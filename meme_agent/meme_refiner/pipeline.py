# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Meme generation pipeline with human-in-the-loop validation.

Uses ADK's LongRunningFunctionTool pattern:
- MemeGenerator calls get_approval tool after generating meme
- Tool returns "pending" while waiting for human input
- Event loop detects long-running function and prompts human
- Human response is sent back to continue the workflow
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
from rich.table import Table

from meme_agent.meme_refiner.agents import (
    create_data_gatherer,
    create_meme_creator,
)
from meme_agent.meme_refiner.prompts import MEME_GENERATOR_INSTRUCTION

# Suppress noisy logs
logging.getLogger("reddit_mcp").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("mcp").setLevel(logging.WARNING)
warnings.filterwarnings("ignore", category=UserWarning)

load_dotenv()
console = Console()

# Model configuration
COHERE_MODEL = "command-a-03-2025"
USER_ID = "user1"
EVENT_COUNT = 0


def log_event(event: Event, phase: str = ""):
    """Pretty print an event with full details."""
    global EVENT_COUNT
    EVENT_COUNT += 1
    
    author = event.author or "System"
    phase_str = f"[{phase}]" if phase else ""
    
    # Header line
    console.print(f"\n[bold cyan]━━━ Event #{EVENT_COUNT:03d} {phase_str} ━━━[/bold cyan]")
    console.print(f"[bold]Author:[/bold] {author}")
    
    # Check for long-running tool
    if event.long_running_tool_ids:
        console.print(f"[bold magenta]⏳ LONG_RUNNING_TOOL detected[/bold magenta]")
        console.print(f"   tool_ids: {event.long_running_tool_ids}")
    
    # Check for final response
    if hasattr(event, 'is_final_response') and event.is_final_response:
        console.print(f"[bold green]🏁 FINAL_RESPONSE[/bold green]")
    
    # Process content parts
    if event.content and event.content.parts:
        for i, part in enumerate(event.content.parts):
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
                # Show full text with nice formatting
                text = part.text.strip()
                if len(text) > 500:
                    console.print(Panel(text[:500] + "...[truncated]", border_style="dim"))
                else:
                    console.print(Panel(text, border_style="dim"))


def generate_imgflip_meme(template_id: int, top_text: str, bottom_text: str) -> dict:
    """Generates a meme using the Imgflip API directly."""
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


def get_approval(meme_url: str, tool_context: ToolContext) -> dict:
    """Long-running function that requests human approval for the meme."""
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
        return {"status": "approved", "meme_url": meme_url, "message": "Meme approved"}
    else:
        console.print("[bold red]❌ Meme rejected by human![/bold red]")
        return {"status": "rejected", "message": "Meme rejected"}


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
    """Generate a meme with human-in-the-loop validation."""
    global EVENT_COUNT
    EVENT_COUNT = 0
    
    # Suppress MCP subprocess output
    server_params = StdioServerParameters(
        command="python3",
        args=["meme_agent/reddit_mcp.py", "--quiet"], 
        env={**os.environ, "PYTHONWARNINGS": "ignore"}
    )

    console.print("[bold cyan]━━━ MEME GENERATION PIPELINE ━━━[/bold cyan]\n")
    
    # Initialize Reddit MCP Toolset
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
    approval_tool = LongRunningFunctionTool(func=get_approval)
    
    # Create agents
    data_gatherer = create_data_gatherer(reddit_toolset)
    meme_creator = create_meme_creator()
    meme_generator = LlmAgent(
        model=LiteLlm(model=COHERE_MODEL),
        name="MemeGenerator",
        instruction=MEME_GENERATOR_INSTRUCTION,
        tools=[meme_tool, approval_tool],
        output_key="meme_url"
    )
    
    pipeline = SequentialAgent(
        name="MemeGeneratorPipeline",
        sub_agents=[data_gatherer, meme_creator, meme_generator],
        description="Three-stage pipeline with human approval"
    )

    session_service = InMemorySessionService()
    runner = Runner(
        app_name='meme_agent',
        agent=pipeline,
        session_service=session_service,
    )
    
    session = await session_service.create_session(
        app_name='meme_agent',
        user_id=USER_ID,
        state={},
    )

    console.print(f"\n[bold]Topic:[/bold] {user_prompt}")
    console.print("[dim]Pipeline: DataGatherer → MemeCreator → MemeGenerator[/dim]")
    console.print("\n[bold cyan]━━━ PHASE 1: Initial Run ━━━[/bold cyan]\n")
    
    final_output = ""
    long_running_function_call = None
    long_running_function_response = None
    
    # Phase 1: Run until we hit the long-running function
    async for event in runner.run_async(
        session_id=session.id,
        user_id=USER_ID,
        new_message=types.Content(role="user", parts=[types.Part(text=user_prompt)])
    ):
        log_event(event, "PHASE1")
        
        # Check for long-running function call
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
        
        # Capture final response text
        if hasattr(event, 'is_final_response') and event.is_final_response and event.content:
            for part in event.content.parts:
                if hasattr(part, 'text') and part.text:
                    final_output = part.text
    
    # Phase 2: Human interaction
    if long_running_function_response:
        console.print("\n[bold cyan]━━━ PHASE 2: Human Decision ━━━[/bold cyan]")
        console.print(f"[dim]Function call ID: {long_running_function_call.id}[/dim]")
        console.print(f"[dim]Current status: {long_running_function_response.response.get('status')}[/dim]\n")
        
        console.print("[bold]Approve this meme? (yes/no):[/bold] ", end="")
        user_input = input().strip().lower()
        approved = user_input in ['yes', 'y', 'approve', 'ok']
        
        console.print(f"\n[bold cyan]━━━ PHASE 3: Resume Pipeline ━━━[/bold cyan]")
        console.print(f"[bold]Sending response:[/bold] confirmed={approved}")
        console.print(f"[dim]Using same function ID: {long_running_function_call.id[:12]}...[/dim]\n")
        
        # Create updated response with SAME ID
        updated_response = long_running_function_response.model_copy(deep=True)
        updated_response.response = {'status': 'approved' if approved else 'rejected'}
        
        # Resume the pipeline
        console.print("[bold yellow]▶️  PIPELINE RESUMED[/bold yellow]\n")
        
        async for event in runner.run_async(
            session_id=session.id,
            user_id=USER_ID,
            new_message=types.Content(
                parts=[types.Part(function_response=updated_response)],
                role='user'
            )
        ):
            log_event(event, "PHASE3")
            
            if hasattr(event, 'is_final_response') and event.is_final_response and event.content:
                for part in event.content.parts:
                    if hasattr(part, 'text') and part.text:
                        final_output = part.text
    
    # Cleanup
    await reddit_toolset.close()
    
    # Summary
    console.print("\n[bold cyan]━━━ PIPELINE COMPLETE ━━━[/bold cyan]")
    console.print(f"[bold]Total events processed:[/bold] {EVENT_COUNT}")
    console.print(f"\n[bold green]Final Output:[/bold green]\n{final_output}")
    
    return {"result": final_output, "state": {}}


def create_meme(user_prompt: str) -> dict[str, Any]:
    """Synchronous wrapper for meme generation."""
    return asyncio.run(generate_meme(user_prompt))
