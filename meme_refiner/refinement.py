"""
Meme Agent Service - CLI Entry Point

Run from project root:
    python -m meme_agent.meme_refiner.refinement "AI taking over jobs"
    
Or directly:
    cd /Users/arpantomar/Documents/meme_service
    python3 meme_agent/meme_refiner/refinement.py "AI taking over jobs"
"""

import sys
import os

# Add project root to path for direct execution
if __name__ == '__main__':
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

from rich.console import Console
from .pipeline import create_meme

console = Console()


def main():
    if len(sys.argv) < 2:
        console.print("[bold red]Usage: python -m meme_agent.meme_refiner.refinement <topic>[/bold red]")
        console.print("[dim]Example: python -m meme_agent.meme_refiner.refinement 'AI taking over jobs'[/dim]")
        sys.exit(1)
    
    topic = " ".join(sys.argv[1:])
    console.print(f"\n[bold cyan]🚀 Starting Meme Generation Pipeline[/bold cyan]")
    console.print(f"[dim]Topic: {topic}[/dim]\n")
    
    result = create_meme(topic)
    
    console.print("\n[bold green]✅ Done![/bold green]")
    return result


if __name__ == '__main__':
    main()
