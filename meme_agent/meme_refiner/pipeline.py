"""
Meme generation pipeline with human-in-the-loop validation and feedback loop.

Architecture:
- Python while loop controls retry on rejection
- SequentialAgent: DataGatherer → MemeCreator → MemeGenerator → ApprovalGateway
- ApprovalGateway uses LongRunningFunctionTool for human approval
- On rejection: collect feedback, update state["refined_prompt"], retry
- On approval: exit loop
"""

import asyncio
import logging
import os
import requests
import warnings
from typing import Any

from dotenv import load_dotenv
from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.events import Event
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import FunctionTool, LongRunningFunctionTool
from google.adk.tools.tool_context import ToolContext
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from google.adk.models.lite_llm import LiteLlm
from google.genai import types
from mcp import StdioServerParameters
from rich.console import Console
from rich.panel import Panel
from google.adk.sessions import DatabaseSessionService

from meme_agent.meme_refiner.agents import (
    create_data_gatherer,
    create_meme_creator,
    create_approval_gateway,
)
from meme_agent.meme_refiner.prompts import MEME_GENERATOR_INSTRUCTION

logging.getLogger("reddit_mcp").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("mcp").setLevel(logging.WARNING)
warnings.filterwarnings("ignore", category=UserWarning)

load_dotenv()
console = Console()

COHERE_MODEL = "command-a-03-2025"
GEMINI_MODEL = "gemini-2.5-flash"
USER_ID = "user1"
EVENT_COUNT = 0
MAX_ITERATIONS = 5
DB_URL = os.getenv("DATABASE_URL")

def log_event(event: Event, phase: str = ""):
    """Pretty print an event with full details."""
    global EVENT_COUNT
    EVENT_COUNT += 1
    
    author = event.author or "System"
    phase_str = f"[{phase}]" if phase else ""
    
    console.print(f"\n[bold cyan]━━━ Event #{EVENT_COUNT:03d} {phase_str} ━━━[/bold cyan]")
    console.print(f"[bold]Author:[/bold] {author}")
    
    if event.long_running_tool_ids:
        console.print(f"[bold magenta]⏳ LONG_RUNNING_TOOL detected[/bold magenta]")
        console.print(f"   tool_ids: {event.long_running_tool_ids}")

    if hasattr(event, 'is_final_response') and event.is_final_response:
        console.print(f"[bold green]🏁 FINAL_RESPONSE[/bold green]")

    if event.content and event.content.parts:
        for part in event.content.parts:
            if hasattr(part, 'function_call') and part.function_call:
                fc = part.function_call
                console.print(f"[bold yellow]📞 FUNCTION_CALL[/bold yellow]")
                console.print(f"   name: {fc.name}")
                console.print(f"   id: {fc.id}")
                if fc.args:
                    console.print(f"   args: {fc.args}")
            
            elif hasattr(part, 'function_response') and part.function_response:
                fr = part.function_response
                console.print(f"[bold blue]📨 FUNCTION_RESPONSE[/bold blue]")
                console.print(f"   id: {fr.id}")
                console.print(f"   name: {fr.name}")
                console.print(f"   response: {fr.response}")
            
            elif hasattr(part, 'text') and part.text:
                console.print(f"[bold white]💬 TEXT OUTPUT[/bold white]")
                text = part.text.strip()
                if len(text) > 500:
                    console.print(Panel(text[:500] + "...[truncated]", border_style="dim"))
                else:
                    console.print(Panel(text, border_style="dim"))


def generate_imgflip_meme(template_id: int, top_text: str, bottom_text: str) -> dict:
    """Generates a meme using the Imgflip API."""
    imgflip_user = os.getenv('IMGFLIP_USERNAME', '')
    imgflip_pass = os.getenv('IMGFLIP_PASSWORD', '')
    
    if not imgflip_user or not imgflip_pass:
        return {"success": False, "url": None, "error": "IMGFLIP credentials not set"}
    
    url = "https://api.imgflip.com/caption_image"
    payload = {
        'template_id': template_id,
        'username': imgflip_user,
        'password': imgflip_pass,
        'text0': top_text,
        'text1': bottom_text
    }

    try:
        response = requests.post(url, data=payload, timeout=10)
        data = response.json()
        
        if data.get('success'):
            return {"success": True, "url": data['data']['url'], "error": None}
        else:
            return {"success": False, "url": None, "error": data.get('error_message', 'Unknown error')}
    except Exception as e:
        return {"success": False, "url": None, "error": str(e)}


def ask_approval(meme_url: str, tool_context: ToolContext) -> dict:
    """
    Long-running function that requests human approval and collects feedback on rejection.
    
    Returns:
        - {"status": "pending"} on first call
        - {"status": "approved", "meme_url": ...} if approved
        - {"status": "rejected", "feedback": ...} if rejected with feedback
    """
    if not tool_context.tool_confirmation:
        console.print("\n[bold yellow]⏸️  PIPELINE PAUSED - Requesting human confirmation[/bold yellow]")
        console.print(Panel(
            f"[bold cyan]🔗 Meme URL:[/bold cyan] {meme_url}\n\n"
            f"[yellow]Please review the meme at the URL above.[/yellow]",
            title="[bold]👤 Human Approval Required[/bold]",
            border_style="yellow"
        ))
        tool_context.request_confirmation(
            hint=f"Approve this meme? {meme_url}",
            payload={"meme_url": meme_url},
        )
        return {"status": "pending", "message": "Waiting for human approval..."}
    
    # Resume - confirmation received
    if tool_context.tool_confirmation.confirmed:
        console.print("[bold green]✅ Meme approved by human![/bold green]")
        return {"status": "approved", "meme_url": meme_url}
    else:
        # Rejected - feedback is in payload
        feedback = tool_context.tool_confirmation.payload.get("feedback", "")
        console.print(f"[bold red]❌ Meme rejected! Feedback: {feedback}[/bold red]")
        return {"status": "rejected", "feedback": feedback}


def get_long_running_function_call(event: Event) -> types.FunctionCall | None:
    """Extract the long-running function call from an event."""
    if not event.long_running_tool_ids or not event.content or not event.content.parts:
        return None
    for part in event.content.parts:
        if part and part.function_call and part.function_call.id in event.long_running_tool_ids:
            return part.function_call
    return None


def get_function_response(event: Event, function_call_id: str) -> types.FunctionResponse | None:
    """Get the function response for a specific function call ID."""
    if not event.content or not event.content.parts:
        return None
    for part in event.content.parts:
        if part and part.function_response and part.function_response.id == function_call_id:
            return part.function_response
    return None


async def generate_meme(user_prompt: str) -> dict[str, Any]:
    """
    Generate a meme with human-in-the-loop validation and feedback loop.
    
    Uses Python while loop for retry:
    - On approval: exit loop
    - On rejection: collect feedback, update refined_prompt, retry
    """
    global EVENT_COUNT
    
    server_params = StdioServerParameters(
        command="python3",
        args=["meme_agent/reddit_mcp.py", "--quiet"], 
        env={**os.environ, "PYTHONWARNINGS": "ignore"}
    )

    console.print("[bold cyan]━━━ MEME GENERATION PIPELINE ━━━[/bold cyan]\n")
    console.print(f"[dim]Max iterations: {MAX_ITERATIONS}[/dim]")
    
    console.print("[dim]Connecting to Reddit MCP...[/dim]")
    reddit_toolset = McpToolset(
        connection_params=StdioConnectionParams(
            server_params=server_params,
            timeout=60.0
        )
    )
    console.print("[green]✓[/green] Reddit MCP ready")
    
    if not os.getenv('IMGFLIP_USERNAME') or not os.getenv('IMGFLIP_PASSWORD'):
        console.print("[yellow]⚠ IMGFLIP credentials not set[/yellow]")
    else:
        console.print("[green]✓[/green] Imgflip credentials found")
    
    # Create tools
    meme_tool = FunctionTool(func=generate_imgflip_meme)
    approval_tool = LongRunningFunctionTool(func=ask_approval)
    
    # Create agents
    data_gatherer = create_data_gatherer(reddit_toolset)
    meme_creator = create_meme_creator()
    meme_generator = LlmAgent(
        model=LiteLlm(model=COHERE_MODEL),
        name="MemeGenerator",
        instruction=MEME_GENERATOR_INSTRUCTION,
        tools=[meme_tool],
        output_key="meme_url"
    )
    approval_gateway = create_approval_gateway(approval_tool)
    
    pipeline = SequentialAgent(
        name="MemeGeneratorPipeline",
        sub_agents=[data_gatherer, meme_creator, meme_generator, approval_gateway],
        description="Four-stage pipeline with human approval gateway"
    )

    # Use InMemorySessionService for reliability (DB can have transient connection issues)
    # Toggle to DatabaseSessionService for production persistence
    if DB_URL:
        try:
            session_service = DatabaseSessionService(db_url=DB_URL)
            console.print("[green]✓[/green] Using DatabaseSessionService")
        except Exception as e:
            console.print(f"[yellow]⚠ DB connection failed, falling back to InMemory: {e}[/yellow]")
            session_service = InMemorySessionService()
    else:
        session_service = InMemorySessionService()
        console.print("[dim]Using InMemorySessionService[/dim]")
    runner = Runner(
        app_name='meme_agent',
        agent=pipeline,
        session_service=session_service,
    )

    console.print(f"\n[bold]Topic:[/bold] {user_prompt}")
    console.print("[dim]Pipeline: DataGatherer → MemeCreator → MemeGenerator → ApprovalGateway[/dim]")
    
    # Initialize structured iteration context
    iteration_context = {
        "initial_prompt": user_prompt,
        "iterations": []  # Will contain meme_spec and human_feedback for each rejected iteration
    }
    approved = False
    final_output = ""
    iteration = 0
    current_meme_spec = None  # Captured from MemeCreator output
    current_meme_url = None   # Captured from MemeGenerator output
    
    session = await session_service.create_session(
            app_name='meme_agent',
            user_id=USER_ID,
            state={"iteration_context": iteration_context},
    )

    # ━━━ RETRY LOOP ━━━
    while not approved and iteration < MAX_ITERATIONS:
        iteration += 1
        EVENT_COUNT = 0
        current_meme_spec = None
        current_meme_url = None
        
        console.print(f"\n[bold magenta]{'━' * 50}[/bold magenta]")
        console.print(f"[bold magenta]   ITERATION {iteration}/{MAX_ITERATIONS}[/bold magenta]")
        console.print(f"[bold magenta]{'━' * 50}[/bold magenta]")
        console.print(f"[bold]Initial prompt:[/bold] {user_prompt}")
        if iteration_context["iterations"]:
            console.print(f"[bold yellow]Previous iterations:[/bold yellow] {len(iteration_context['iterations'])}")
            for prev in iteration_context["iterations"]:
                console.print(f"  - Iter {prev['iteration']}: {prev['meme_spec'].get('template_name', 'unknown')} → Feedback: {prev['human_feedback']}")
        
        long_running_function_call = None
        long_running_function_response = None
        
        console.print(f"\n[bold cyan]━━━ PHASE 1: Pipeline Execution ━━━[/bold cyan]\n")
        
        # Update session state with current iteration_context
        session.state["iteration_context"] = iteration_context
        
        # Run pipeline - pass the initial prompt (agents read context from state)
        async for event in runner.run_async(
            session_id=session.id,
            user_id=USER_ID,
            new_message=types.Content(role="user", parts=[types.Part(text=user_prompt)])
        ):
            log_event(event, "RUN")
            
            # Capture meme_spec from MemeCreator output (it's a JSON in text)
            if hasattr(event, 'author') and event.author == 'MemeCreator':
                if hasattr(event, 'content') and event.content:
                    for part in event.content.parts:
                        if hasattr(part, 'text') and part.text:
                            try:
                                import json
                                # Try to parse JSON from the output
                                text = part.text.strip()
                                if text.startswith('```json'):
                                    text = text[7:]
                                if text.startswith('```'):
                                    text = text[3:]
                                if text.endswith('```'):
                                    text = text[:-3]
                                current_meme_spec = json.loads(text.strip())
                            except (json.JSONDecodeError, Exception):
                                pass  # Not JSON, skip
            
            # Capture meme_url from generate_imgflip_meme response
            if hasattr(event, 'content') and event.content:
                for part in event.content.parts:
                    if hasattr(part, 'function_response') and part.function_response:
                        if part.function_response.name == 'generate_imgflip_meme':
                            resp = part.function_response.response
                            if resp and resp.get('success') and resp.get('url'):
                                current_meme_url = resp['url']
            
            # Detect long-running function call
            if not long_running_function_call:
                lrf = get_long_running_function_call(event)
                if lrf:
                    long_running_function_call = lrf
                    console.print(f"\n[bold magenta]🔍 Detected long-running call: id={lrf.id[:12]}...[/bold magenta]")
            else:
                _potential_response = get_function_response(event, long_running_function_call.id)
                if _potential_response:
                    long_running_function_response = _potential_response
                    console.print(f"[bold magenta]📦 Captured pending response: status={_potential_response.response.get('status')}[/bold magenta]")
            
            if hasattr(event, 'is_final_response') and event.is_final_response and event.content:
                for part in event.content.parts:
                    if hasattr(part, 'text') and part.text:
                        final_output = part.text
        
        # Handle human interaction
        if long_running_function_response:
            console.print(f"\n[bold cyan]━━━ PHASE 2: Human Decision ━━━[/bold cyan]")
            console.print(f"[dim]Function call ID: {long_running_function_call.id}[/dim]\n")
            
            console.print("[bold]Approve this meme? (yes/no):[/bold] ", end="")
            user_input = input().strip().lower()
            
            if user_input.strip().lower() in ['yes', 'y', 'approve', 'ok']:
                approved = True
                feedback = ""
            else:
                approved = False
                console.print("[bold]Please provide feedback to improve the meme:[/bold] ", end="")
                feedback = input().strip()
                
                # Append iteration to history
                iteration_data = {
                    "iteration": iteration,
                    "meme_spec": current_meme_spec or {"error": "Failed to capture meme spec"},
                    "meme_url": current_meme_url,
                    "human_feedback": feedback
                }
                iteration_context["iterations"].append(iteration_data)
                
                console.print(f"\n[bold yellow]📝 Added iteration {iteration} to history[/bold yellow]")
                console.print(f"[dim]Template: {current_meme_spec.get('template_name', 'unknown') if current_meme_spec else 'N/A'}[/dim]")
                console.print(f"[dim]Feedback: {feedback}[/dim]")
            
            console.print(f"\n[bold cyan]━━━ PHASE 3: Resume Pipeline ━━━[/bold cyan]")
            console.print(f"[bold]Sending response:[/bold] confirmed={approved}, feedback={feedback}")
            
            # Create updated response with SAME ID
            updated_response = long_running_function_response.model_copy(deep=True)
            updated_response.response = {
                'confirmed': approved,
                'feedback': feedback
            }
            
            console.print("[bold yellow]▶️  PIPELINE RESUMED[/bold yellow]\n")
            
            async for event in runner.run_async(
                session_id=session.id,
                user_id=USER_ID,
                new_message=types.Content(
                    parts=[types.Part(function_response=updated_response)],
                    role='user'
                )
            ):
                log_event(event, "RESUME")
                
                if hasattr(event, 'is_final_response') and event.is_final_response and event.content:
                    for part in event.content.parts:
                        if hasattr(part, 'text') and part.text:
                            final_output = part.text
            
            if approved:
                console.print("\n[bold green]✅ MEME APPROVED - Exiting loop[/bold green]")
            else:
                console.print(f"\n[bold yellow]❌ MEME REJECTED - Retrying with feedback ({MAX_ITERATIONS - iteration} attempts remaining)[/bold yellow]")
        else:
            console.print("[bold red]No approval request detected - something went wrong[/bold red]")
            break
    
    # Cleanup
    await reddit_toolset.close()
    
    # Summary
    console.print(f"\n[bold cyan]{'━' * 50}[/bold cyan]")
    console.print(f"[bold cyan]   PIPELINE COMPLETE[/bold cyan]")
    console.print(f"[bold cyan]{'━' * 50}[/bold cyan]")
    console.print(f"[bold]Iterations used:[/bold] {iteration}/{MAX_ITERATIONS}")
    console.print(f"[bold]Final status:[/bold] {'✅ Approved' if approved else '❌ Rejected (max iterations)'}")
    console.print(f"\n[bold green]Final Output:[/bold green]\n{final_output}")
    
    return {"result": final_output, "approved": approved, "iterations": iteration}


def create_meme(user_prompt: str) -> dict[str, Any]:
    """Synchronous wrapper for meme generation."""
    return asyncio.run(generate_meme(user_prompt))
