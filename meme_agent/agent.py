"""
Meme Agent Service - Multi-Agent Meme Generation Pipeline

This module provides the main entry point for generating memes based on user prompts.
It uses a SequentialAgent to orchestrate three agents in a pipeline:

1. Prompt Optimizer (Agent1): Transforms user input into optimized search queries
   - Stores output in state['optimized_prompt']

2. Web Scraper (Agent2): Uses Scrapeless MCP server to scrape meme content
   - Reads from state['optimized_prompt']
   - Stores output in state['meme_spec']

3. Meme Generator (Agent3): Creates the actual meme using meme-mcp server
   - Reads from state['meme_spec']
   - Stores output in state['meme_result']

Usage:
    # Via command line
    python3 agent.py "Make a meme about programmers debugging code"
"""

import asyncio
import json
import os
import re
from typing import Any

import requests

from dotenv import load_dotenv
from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from google.genai import types
from google.adk.models.lite_llm import LiteLlm 
from mcp import StdioServerParameters
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
import litellm
console = Console()

load_dotenv()

GEMINI_MODEL = 'gemini-2.5-flash-lite'
COMMAND_MODEL="command-a-03-2025"
COHERE_MODEL="command-a-03-2025"
OLLAMA_API_BASE = os.getenv("OLLAMA_API_BASE", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
ollama_llm = LiteLlm(
    model=f"ollama_chat/{OLLAMA_MODEL}",
    api_base=OLLAMA_API_BASE,
)


DATA_GATHERER_INSTRUCTION = '''You are a research assistant that gathers Reddit content.

## YOUR TASK:
Given a user's topic, generate 3-5 related search queries and call the mine_reddit_context tool with ALL topics as a list.

For example, if the user says "AI taking over jobs", call mine_reddit_context with:
["AI replacing programmers", "ChatGPT vs human workers", "automation job loss memes", "robots taking jobs funny"]

## OUTPUT:
After receiving the tool response, output ALL the gathered data exactly as received.
Do not analyze or summarize - just pass through the raw data for the next agent.
'''


MEME_CREATOR_INSTRUCTION = '''You are a meme creation expert. Your ONLY job is to output a JSON object.

## INPUT:
You will receive Reddit data from {reddit_data} about a topic.

## YOUR TASK:
1. Analyze the Reddit data to understand the sentiment and humor
2. Choose the BEST meme template that matches the content (DO NOT default to Distracted Boyfriend)
3. Write clever, relevant text for the meme

## CRITICAL: OUTPUT ONLY JSON
You MUST output ONLY a valid JSON object. No explanations, no prose, no markdown - JUST JSON.

```json
{
    "topics_searched": ["topic1", "topic2"],
    "insights": "Brief summary of what you found",
    "meme_template_id": <TEMPLATE_ID_FROM_LIST>,
    "template_name": "<TEMPLATE_NAME>",
    "top_text": "Your top text here",
    "bottom_text": "Your bottom text here",
    "reasoning": "Why this template and text combination works"
}
```

## AVAILABLE TEMPLATES (CHOOSE THE BEST ONE FOR THE CONTENT):

**Comparison/Preference:**
- Drake Hotline Bling (181913649): Top=reject, Bottom=prefer
- Tuxedo Winnie The Pooh (178591752): Top=basic, Bottom=fancy

**Jealousy/Distraction:**
- Distracted Boyfriend (112126428): Three-way comparison
- I Bet He's Thinking About Other Women (119139145): Inner thoughts

**Frustration/Chaos:**
- This Is Fine (55311130): Ignoring problems
- Panik Kalm Panik (222403160): Panic-calm-panic cycle
- Clown Applying Makeup (195515965): Fooling yourself

**Arguments/Logic:**
- Change My Mind (129242436): Hot take/opinion
- Hard To Swallow Pills (135256802): Uncomfortable truth
- One Does Not Simply (61579): Something difficult

**Reactions:**
- Woman Yelling At Cat (188390779): Argument vs chill response
- Batman Slapping Robin (438680): Shutting someone down
- Mocking SpongeBob (102156234): Mocking text

**Decisions:**
- Two Buttons (87743020): Difficult choice
- Uno Draw 25 Cards (217743513): Refuse vs extreme option
- Left Exit 12 Off Ramp (124822590): Last-minute decision

**Revelations:**
- Always Has Been (252600902): Something was always true
- They're The Same Picture (180190441): Two things are identical

**Star Wars:**
- Anakin Padme 4 Panel (322841258): Misunderstanding

REMINDER: Choose a template that FITS the content. Output ONLY the JSON object.
'''

MEME_GENERATOR_INSTRUCTION = '''You are a meme generator. Your job is to use the generate_meme tool.

## INPUT:
You will receive a meme specification from {meme_spec} containing:
- meme_template_id: A numeric ID
- top_text: Text for the top of the meme
- bottom_text: Text for the bottom of the meme

## YOUR TASK:
1. Extract the template_id, top_text, and bottom_text from the specification
2. Call the generate_meme tool with these parameters
3. Return ONLY the meme URL from the tool response

## OUTPUT FORMAT:
After calling the tool, output ONLY the meme URL like this:
https://i.imgflip.com/xxxxx.jpg

Nothing else. Just the URL.
'''


def generate_imgflip_meme(template_id: int, top_text: str, bottom_text: str) -> dict:
    """
    Generates a meme using the Imgflip API directly.
    
    Args:
        template_id: The numeric ID of the meme template.
        top_text: Text to appear at the top.
        bottom_text: Text to appear at the bottom.
        
    Returns:
        dict with 'success', 'url', and 'error' keys.
    """
    imgflip_user = os.getenv('IMGFLIP_USERNAME', '')
    imgflip_pass = os.getenv('IMGFLIP_PASSWORD', '')
    
    if not imgflip_user or not imgflip_pass:
        return {
            "success": False,
            "url": None,
            "error": "IMGFLIP credentials not set"
        }
    
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
            return {
                "success": True,
                "url": data['data']['url'],
                "error": None
            }
        else:
            return {
                "success": False,
                "url": None,
                "error": data.get('error_message', 'Unknown error')
            }
    except Exception as e:
        return {
            "success": False,
            "url": None,
            "error": str(e)
        }


def parse_meme_spec(text: str) -> dict | None:
    """
    Parse JSON meme specification from MemeCreator output.
    Handles JSON wrapped in markdown code blocks.
    """
    # Try to extract JSON from code blocks first
    json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if json_match:
        json_str = json_match.group(1).strip()
    else:
        json_str = text.strip()
    
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return None



async def generate_meme(user_prompt: str) -> dict[str, Any]:
    """
    Generate a meme based on the user's prompt.
    
    Pipeline:
    1. DataGatherer (Cohere) - Gathers Reddit data using MCP tool
    2. MemeCreator (Ollama) - Analyzes data and outputs JSON meme spec
    3. Direct imgflip API call - Creates the actual meme
    
    Args:
        user_prompt: The user's description of the meme they want to create.
        
    Returns:
        dict: Contains the result of the meme generation.
    """
    server_params = StdioServerParameters(
        command="python3",
        args=["meme_agent/reddit_mcp.py"], 
    )

    # 1. Initialize Reddit MCP Toolset
    console.print("[bold yellow]🔌 Connecting to Custom Reddit Miner...[/bold yellow]")
    reddit_toolset = McpToolset(
        connection_params=StdioConnectionParams(
            server_params=server_params,
            timeout=60.0
        )
    )
    
    imgflip_username = os.getenv('IMGFLIP_USERNAME', '')
    imgflip_password = os.getenv('IMGFLIP_PASSWORD', '')
    
    if not imgflip_username or not imgflip_password:
        console.print(Panel(
            "[bold yellow]IMGFLIP credentials not set - meme generation will not work[/bold yellow]",
            border_style="yellow",
        ))
    else:
        console.print("[green]✅ Imgflip credentials found[/green]")
    
    console.print("[bold yellow]🔌 Connecting to Imgflip MCP Server...[/bold yellow]")
    imgflip_server_params = StdioServerParameters(
        command="python3",
        args=["meme_agent/imgflip_mcp.py"],
    )
    imgflip_toolset = McpToolset(
        connection_params=StdioConnectionParams(
            server_params=imgflip_server_params,
            timeout=30.0
        )
    )
    console.print("[green]✅ Imgflip MCP ready[/green]")
    
    data_gatherer = LlmAgent(
        model=LiteLlm(model=COHERE_MODEL),
        name="DataGatherer",
        instruction=DATA_GATHERER_INSTRUCTION,
        tools=[reddit_toolset],
        output_key="reddit_data"
    )

    meme_creator = LlmAgent(
        model=LiteLlm(model=COHERE_MODEL),
        name="MemeCreator",
        instruction=MEME_CREATOR_INSTRUCTION,
        output_key="meme_spec"
    )
    
    meme_generator = LlmAgent(
        model=LiteLlm(model=COHERE_MODEL),
        name="MemeGenerator",
        instruction=MEME_GENERATOR_INSTRUCTION,
        tools=[imgflip_toolset],
        output_key="meme_url"
    )
    
    pipeline = SequentialAgent(
        name="MemeGeneratorPipeline",
        sub_agents=[data_gatherer, meme_creator, meme_generator],
        description="Three-stage pipeline: gather Reddit data, create meme spec, generate meme"
    )

    session_service = InMemorySessionService()
    runner = Runner(
        app_name='meme_agent',
        agent=pipeline,
        session_service=session_service,
    )
    session = await session_service.create_session(
        app_name='meme_agent',
        user_id="user1",
        state={},
    )

    topic = user_prompt
    console.print(f"\n[bold cyan]🤖 Topic: {topic}[/bold cyan]")
    console.print("[dim]Pipeline: DataGatherer (Cohere) → MemeCreator (Cohere) → MemeGenerator (Cohere)[/dim]\n")
    
    final_output = ""
    async for event in runner.run_async(
        user_id="user1",
        session_id=session.id,
        new_message=types.Content(
            role="user",
            parts=[types.Part(text=topic)]
        )
    ):
        console.log(f"[bold blue]TRACE[/bold blue] Received event: [bold cyan]{type(event).__name__}[/bold cyan]")
            
        # Show which agent is active
        if hasattr(event, 'author') and event.author:
            agent_name = event.author
            if agent_name == "DataGatherer":
                console.print(f"[yellow]📡 DataGatherer[/yellow]", end=" ")
            elif agent_name == "MemeCreator":
                console.print(f"[green]🎨 MemeCreator[/green]", end=" ")
            elif agent_name == "MemeGenerator":
                console.print(f"[magenta]🖼️ MemeGenerator[/magenta]", end=" ")
        
        # Capture final response (from MemeGenerator)
        if event.is_final_response and event.content:
            for part in event.content.parts:
                if hasattr(part, 'text') and part.text:
                    final_output = part.text
        
        # Print function calls
        if hasattr(event, 'content') and event.content:
            for part in event.content.parts:
                if hasattr(part, 'function_call') and part.function_call:
                    console.print(f"[dim]Calling tool: {part.function_call.name}[/dim]")
    
    # Close toolsets
    await reddit_toolset.close()
    await imgflip_toolset.close()
    
    # 8. Display result
    console.print("\n[bold green]=== FINAL MEME RESULT ===[/bold green]")
    console.print(final_output)
    
    return {
        "result": final_output,
        "state": {}
    }


def create_meme(user_prompt: str) -> dict[str, Any]:
    """
    Synchronous wrapper for meme generation.
    """
    return asyncio.run(generate_meme(user_prompt))


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1:
        prompt = ' '.join(sys.argv[1:])
    else:
        console.print('[bold cyan]Enter your meme idea:[/bold cyan] ', end='')
        prompt = input()
    
    console.print()
    console.print(Panel(
        f'[bold white]{prompt}[/bold white]',
        title='🎨 Meme Request',
        border_style='magenta',
    ))
    
    try:
        result = create_meme(prompt)
        
        if 'state' in result and result['state']:
            state = result['state']
            
            table = Table(title='📊 Pipeline State Summary', show_header=True, header_style='bold cyan')
            table.add_column('Agent', style='cyan')
            table.add_column('Output Key', style='yellow')
            table.add_column('Status', style='green')
            
            if 'optimized_prompt' in state:
                table.add_row('prompt_optimizer', 'optimized_prompt', '✅ Stored')
            if 'meme_spec' in state:
                table.add_row('web_scraper', 'meme_spec', '✅ Stored')
            if 'meme_result' in state:
                table.add_row('meme_generator', 'meme_result', '✅ Stored')
            
            console.print()
            console.print(table)
        
        console.print()
        if result['result']:
            console.print(Panel(
                str(result['result']),
                title='Final Result',
                border_style='green',
            ))
        
    except ValueError as e:
        console.print()
        console.print(Panel(
            f'[bold red]{e}[/bold red]',
            title='❌ Validation Error',
            border_style='red',
        ))
        sys.exit(1)
    except Exception as e:
        console.print()
        import traceback
        console.print(Panel(
            f'[bold red]{e}[/bold red]\n\n[dim]{traceback.format_exc()}[/dim]',
            title='❌ Error',
            border_style='red',
        ))
        sys.exit(1)
