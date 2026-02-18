"""
Meme generation pipeline with human-in-the-loop validation and feedback loop.

Architecture:
- Python while loop controls retry on rejection
- SequentialAgent: DataGatherer → MemeCreator → MemeGenerator → ApprovalGateway
- ApprovalGateway uses LongRunningFunctionTool for human approval
- On rejection: collect feedback, update iteration_context, retry
- On approval: exit loop
"""

import asyncio
import logging
import os
import warnings
from typing import Any

from google.adk.agents import SequentialAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService, DatabaseSessionService
from google.adk.tools import FunctionTool, LongRunningFunctionTool
try:
    from google.adk.tools.mcp_tool import McpToolset
except ImportError:
    from google.adk.tools.mcp_tool import MCPToolset as McpToolset

from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from google.adk.models.lite_llm import LiteLlm
from google.genai import types
from mcp import StdioServerParameters
from rich.console import Console

# Local imports from modular structure
from .config import (
    MAX_ITERATIONS,
    USER_ID,
    DB_URL,
)
from .agents import (
    create_data_gatherer,
    create_meme_creator,
    create_meme_generator,
    create_approval_gateway,
)
from .tools import ask_approval
from .logging_utils import log_event, reset_event_count
from .event_handlers import (
    get_long_running_function_call,
    get_function_response,
    extract_meme_spec,
    extract_meme_url,
)
from .utils import generate_imgflip_meme

# Configure logging
logging.getLogger("reddit_mcp").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("mcp").setLevel(logging.WARNING)
warnings.filterwarnings("ignore", category=UserWarning)

console = Console()


def _create_session_service():
    """
    Create the appropriate session service based on configuration.
    
    Uses DatabaseSessionService if DB_URL is configured, 
    otherwise falls back to InMemorySessionService.
    
    Returns:
        Session service instance.
    """
    if DB_URL:
        try:
            service = DatabaseSessionService(db_url=DB_URL)
            console.print("[green]✓[/green] Using DatabaseSessionService")
            return service
        except Exception as e:
            console.print(f"[yellow]⚠ DB connection failed, falling back to InMemory: {e}[/yellow]")
            return InMemorySessionService()
    else:
        console.print("[dim]Using InMemorySessionService[/dim]")
        return InMemorySessionService()


def _create_pipeline(reddit_toolset):
    """
    Create the meme generation pipeline with all agents.
    
    Args:
        reddit_toolset: MCPToolset for Reddit data gathering.
        
    Returns:
        Tuple of (pipeline, meme_tool, approval_tool) for use in runner.
    """
    meme_tool = FunctionTool(func=generate_imgflip_meme)
    approval_tool = LongRunningFunctionTool(func=ask_approval)
    
    data_gatherer = create_data_gatherer(reddit_toolset)
    meme_creator = create_meme_creator()
    meme_generator = create_meme_generator([meme_tool])
    approval_gateway = create_approval_gateway(approval_tool)
    
    pipeline = SequentialAgent(
        name="MemeGeneratorPipeline",
        sub_agents=[data_gatherer, meme_creator, meme_generator, approval_gateway],
        description="Four-stage pipeline with human approval gateway"
    )
    
    return pipeline, approval_tool


async def _handle_human_decision(
    long_running_function_call,
    long_running_function_response,
    iteration: int,
    iteration_context: dict,
    current_meme_spec: dict | None,
    current_meme_url: str | None,
    feedback_handler: Any = None,
) -> tuple[bool, str]:
    """
    Handle the human approval/rejection decision.
    
    Args:
        long_running_function_call: The pending function call.
        long_running_function_response: The pending function response.
        iteration: Current iteration number.
        iteration_context: The iteration history context.
        current_meme_spec: Captured meme specification.
        current_meme_url: Captured meme URL.
        feedback_handler: Async callback to request feedback from external system.
        
    Returns:
        Tuple of (approved: bool, feedback: str).
    """
    console.print(f"\n[bold cyan]━━━ PHASE 2: Human Decision ━━━[/bold cyan]")
    console.print(f"[dim]Function call ID: {long_running_function_call.id}[/dim]\n")
    
    if not feedback_handler:
        # Fallback meant to be removed, but kept as error handler
        console.print("[bold red]❌ No feedback handler provided! Cannot proceed in WebSocket mode.[/bold red]")
        return False, "No feedback handler provided"
        
    console.print("[bold yellow]⏳ Waiting for external feedback via WebSocket...[/bold yellow]")
    
    # Prepare payload for the handler
    payload = {
        "type": "approval_request",
        "meme_url": current_meme_url,
        "meme_spec": current_meme_spec,
        "iteration": iteration,
        "command_id": long_running_function_call.id
    }
    
    # Await the external decision
    decision = await feedback_handler(payload)
    
    approved = decision.get("approved", "false")
    feedback = decision.get("feedback", "")
    
    if approved=="true":
        console.print("[bold green]✅ Approved via WebSocket[/bold green]")
        return True, ""
    
    # Rejection flow
    console.print(f"[bold red]❌ Rejected via WebSocket. Feedback: {feedback}[/bold red]")
    
    # Append iteration to history
    iteration_data = {
        "iteration": iteration,
        "meme_spec": current_meme_spec or {"error": "Failed to capture meme spec"},
        "meme_url": current_meme_url,
        "human_feedback": feedback
    }
    iteration_context["iterations"].append(iteration_data)
    
    return False, feedback


async def _run_pipeline_iteration(
    runner,
    session,
    user_prompt: str,
    iteration_context: dict,
    feedback_handler: Any = None,
) -> tuple:
    """
    Run a single iteration of the pipeline.
    
    Args:
        runner: ADK Runner instance.
        session: Current session.
        user_prompt: User's meme topic.
        iteration_context: Context containing previous iteration history.
        
    Returns:
        Tuple of (long_running_call, long_running_response, meme_spec, meme_url, final_output).
    """
    long_running_function_call = None
    long_running_function_response = None
    current_meme_spec = None
    current_meme_url = None
    final_output = ""
    
    # Update session state with current iteration_context
    session.state["iteration_context"] = iteration_context
    
    async for event in runner.run_async(
        session_id=session.id,
        user_id=USER_ID,
        new_message=types.Content(role="user", parts=[types.Part(text=user_prompt)])
    ):
        log_event(event, "RUN")
        
        if feedback_handler:
            
            log_msg = ""
            if event.author=="DataGatherer":
                log_msg="Exploring Reddit for trends..."
            elif event.author=="MemeCreator":
                log_msg="Generating meme specifications"
            elif event.author=="MemeGenerator":
                log_msg="Generating meme image"
            
            if log_msg:
               await feedback_handler({
                   "type": "event_log",
                   "message": log_msg
               })
        
        spec = extract_meme_spec(event)
        if spec:
            current_meme_spec = spec
            if feedback_handler:
                await feedback_handler({
                    "type": "event_log",
                    "message": "Planning meme specifications..."
                })
        
        
        url = extract_meme_url(event)
        if url:
            current_meme_url = url
        
        
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
    
    return (
        long_running_function_call,
        long_running_function_response,
        current_meme_spec,
        current_meme_url,
        final_output,
    )


async def _resume_pipeline(
    runner,
    session,
    long_running_function_response,
    approved: bool,
    feedback: str,
) -> str:
    """
    Resume the pipeline after human decision.
    
    Args:
        runner: ADK Runner instance.
        session: Current session.
        long_running_function_response: The pending response to update.
        approved: Whether the meme was approved.
        feedback: Feedback if rejected.
        
    Returns:
        Final output text from the resumed pipeline.
    """
    console.print(f"\n[bold cyan]━━━ PHASE 3: Resume Pipeline ━━━[/bold cyan]")
    console.print(f"[bold]Sending response:[/bold] confirmed={approved}, feedback={feedback}")
    
    # Create updated response with SAME ID
    updated_response = long_running_function_response.model_copy(deep=True)
    updated_response.response = {
        'confirmed': approved,
        'feedback': feedback
    }
    
    console.print("[bold yellow]▶️  PIPELINE RESUMED[/bold yellow]\n")
    
    final_output = ""
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
    
    return final_output


async def generate_meme(user_prompt: str, feedback_handler: Any = None) -> dict[str, Any]:
    """
    Generate a meme with human-in-the-loop validation and feedback loop.
    
    Uses Python while loop for retry:
    - On approval: exit loop
    - On rejection: collect feedback, update iteration_context, retry
    
    Args:
        user_prompt: The meme topic/prompt from the user.
        feedback_handler: Async callback for HITL.
        
    Returns:
        Dict with 'result', 'approved', 'iterations', and 'meme_url' keys.
    """
    server_params = StdioServerParameters(
        command="python3",
        args=["meme_refiner/reddit_mcp.py", "--quiet"], 
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
    
    # Create pipeline and services
    pipeline, _ = _create_pipeline(reddit_toolset)
    session_service = _create_session_service()
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
        "iterations": []
    }
    approved = False
    final_output = ""
    iteration = 0
    
    session = await session_service.create_session(
        app_name='meme_agent',
        user_id=USER_ID,
        state={"iteration_context": iteration_context},
    )

    # ━━━ RETRY LOOP ━━━
    while not approved and iteration < MAX_ITERATIONS:
        iteration += 1
        reset_event_count()
        
        console.print(f"\n[bold magenta]{'━' * 50}[/bold magenta]")
        console.print(f"[bold magenta]   ITERATION {iteration}/{MAX_ITERATIONS}[/bold magenta]")
        console.print(f"[bold magenta]{'━' * 50}[/bold magenta]")
        console.print(f"[bold]Initial prompt:[/bold] {user_prompt}")
        
        if iteration_context["iterations"]:
            console.print(f"[bold yellow]Previous iterations:[/bold yellow] {len(iteration_context['iterations'])}")
            for prev in iteration_context["iterations"]:
                template_name = prev['meme_spec'].get('template_name', 'unknown') if prev.get('meme_spec') else 'N/A'
                console.print(f"  - Iter {prev['iteration']}: {template_name} → Feedback: {prev['human_feedback']}")
        
        console.print(f"\n[bold cyan]━━━ PHASE 1: Pipeline Execution ━━━[/bold cyan]\n")
        
        # Run pipeline iteration
        (
            long_running_function_call,
            long_running_function_response,
            current_meme_spec,
            current_meme_url,
            final_output,
        ) = await _run_pipeline_iteration(runner, session, user_prompt, iteration_context, feedback_handler)
        
        # Handle human interaction
        if long_running_function_response:
            approved, feedback = await _handle_human_decision(
                long_running_function_call,
                long_running_function_response,
                iteration,
                iteration_context,
                current_meme_spec,
                current_meme_url,
                feedback_handler=feedback_handler,
            )
            
            # Resume pipeline
            final_output = await _resume_pipeline(
                runner,
                session,
                long_running_function_response,
                approved,
                feedback,
            )
            
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
    
    return {
        "result": final_output,
        "approved": approved,
        "iterations": iteration,
        "meme_url": current_meme_url
    }


def create_meme(user_prompt: str) -> dict[str, Any]:
    """Synchronous wrapper for meme generation."""
    return asyncio.run(generate_meme(user_prompt))
