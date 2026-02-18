
"""
Imgflip MCP Server - Generates memes using the Imgflip API.

This MCP server provides a tool for generating memes via the imgflip.com API.
It's designed to be used by Google ADK agents.

Usage:
    python meme_agent/imgflip_mcp.py
"""

import logging
import os
import sys

import requests
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

logging.basicConfig(
    level=logging.DEBUG,
    format='[%(levelname)s] imgflip_mcp: %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger(__name__)

mcp = FastMCP("ImgflipMemeGenerator")

# Common meme template IDs for reference
MEME_TEMPLATES = {
    # --- The Classics ---
    "Drake Hotline Bling": 181913649,
    "Distracted Boyfriend": 112126428,
    "Two Buttons": 87743020,
    "Change My Mind": 129242436,
    "Expanding Brain": 93895088,
    "Left Exit 12 Off Ramp": 124822590,
    "Batman Slapping Robin": 438680,
    "Mocking SpongeBob": 102156234,
    "Woman Yelling At Cat": 188390779,
    "This Is Fine": 55311130,
    
    # --- The "Argument" & "Logic" Memes ---
    "One Does Not Simply": 61579,
    "Hard To Swallow Pills": 135256802,
    "Tuxedo Winnie The Pooh": 178591752,
    "Panik Kalm Panik": 222403160,
    "Buff Doge vs. Cheems": 247375501,
    "Trade Offer": 309868304,
    "Clown Applying Makeup": 195515965,
    "Is This A Pigeon": 100777631,
    "Boardroom Meeting Suggestion": 444501,
    
    # --- The "Decision" & "Reaction" Memes ---
    "Epic Handshake": 135678846,
    "Sad Pablo Escobar": 8072285,
    "Disaster Girl": 370867422,
    "Running Away Balloon": 131940431,
    "Uno Draw 25 Cards": 217743513,
    "Finding Neverland": 6235864,
    "Always Has Been": 252600902,
    "Waiting Skeleton": 4087833,
    "Sleeping Shaq": 175540452,
    
    # --- The "Comparison" Memes ---
    "They're The Same Picture": 180190441,
    "Swole Doge vs Cheems": 247375501,
    "Who Killed Hannibal (Why Would X Do This)": 14230520,
    "Monkey Puppet (Looking Away)": 161865971,
    "I Bet He's Thinking About Other Women": 119139145,
    
    # --- Star Wars ---
    "Anakin Padme 4 Panel": 322841258,
    "Star Wars Yoda": 14371066,
    "Obi Wan Kenobi Hello There": 179099511
}


@mcp.tool()
def generate_meme(template_id: int, top_text: str, bottom_text: str) -> str:
    """
    Generates a meme using the Imgflip API.
    
    Args:
        template_id: The numeric ID of the meme template (e.g., 181913649 for Drake).
        top_text: Text to appear at the top/first position of the meme.
        bottom_text: Text to appear at the bottom/second position of the meme.
        
    Returns:
        JSON string with success status and meme URL or error message.
    """
    logger.info(f"=== Generating meme with template {template_id} ===")
    logger.info(f"Top text: {top_text}")
    logger.info(f"Bottom text: {bottom_text}")
    
    imgflip_user = os.getenv('IMGFLIP_USERNAME', '')
    imgflip_pass = os.getenv('IMGFLIP_PASSWORD', '')
    
    if not imgflip_user or not imgflip_pass:
        logger.error("IMGFLIP credentials not set")
        return '{"success": false, "url": null, "error": "IMGFLIP credentials not set in environment"}'
    
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
            meme_url = data['data']['url']
            logger.info(f"SUCCESS! Meme URL: {meme_url}")
            return f'{{"success": true, "url": "{meme_url}", "error": null}}'
        else:
            error_msg = data.get('error_message', 'Unknown error')
            logger.error(f"Imgflip API error: {error_msg}")
            return f'{{"success": false, "url": null, "error": "{error_msg}"}}'
    except Exception as e:
        logger.error(f"Request failed: {e}")
        return f'{{"success": false, "url": null, "error": "{str(e)}"}}'


@mcp.tool()
def list_templates() -> str:
    """
    Lists available meme templates with their IDs.
    
    Returns:
        JSON string with available template names and IDs.
    """
    templates = [f'"{name}": {tid}' for name, tid in MEME_TEMPLATES.items()]
    return "{" + ", ".join(templates) + "}"


if __name__ == "__main__":
    logger.info("Launching Imgflip MCP server...")
    mcp.run()
