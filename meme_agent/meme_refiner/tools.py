
"""
Tool functions for the meme generation pipeline.

This module contains the long-running approval tool that handles
human-in-the-loop validation.
"""

from rich.console import Console
from rich.panel import Panel

from google.adk.tools.tool_context import ToolContext

console = Console()


def ask_approval(meme_url: str, tool_context: ToolContext) -> dict:
    """
    Long-running function that requests human approval and collects feedback on rejection.
    
    This is a LongRunningFunctionTool that pauses the pipeline to allow human review
    of the generated meme. On rejection, it collects feedback to improve the next iteration.
    
    Args:
        meme_url: URL of the generated meme to be reviewed.
        tool_context: ADK tool context for managing confirmation flow.
        
    Returns:
        - {"status": "pending"} on first call (waiting for human input)
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
