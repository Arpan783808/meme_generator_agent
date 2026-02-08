
"""
Logging utilities for the meme generation pipeline.

This module provides pretty-printing and logging functions for ADK events.
"""

from rich.console import Console
from rich.panel import Panel

from google.adk.events import Event

console = Console()

# Global event counter for tracking
_event_count = 0


def reset_event_count():
    """Reset the event counter to zero."""
    global _event_count
    _event_count = 0


def get_event_count() -> int:
    """Get the current event count."""
    return _event_count


def log_event(event: Event, phase: str = "") -> None:
    """
    Pretty print an ADK event with full details.
    
    Logs function calls, responses, and text output with color-coded formatting
    using Rich console for enhanced visibility.
    
    Args:
        event: The ADK Event object to log.
        phase: Optional phase label (e.g., "RUN", "RESUME") for context.
    """
    global _event_count
    _event_count += 1
    
    author = event.author or "System"
    phase_str = f"[{phase}]" if phase else ""
    
    console.print(f"\n[bold cyan]━━━ Event #{_event_count:03d} {phase_str} ━━━[/bold cyan]")
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
