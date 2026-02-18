
"""
Utility functions for meme generation.

This module provides helper functions for interacting with external APIs
and parsing data structures.
"""

import json
import os
import re
from typing import Any

import requests


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
    
    Args:
        text: Raw text output from MemeCreator agent.
        
    Returns:
        Parsed JSON dict or None if parsing fails.
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
