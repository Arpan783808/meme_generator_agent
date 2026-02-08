"""
Event handler utilities for the meme generation pipeline.

This module provides functions for extracting and processing ADK events,
particularly for handling long-running function calls.
"""

import json
from typing import Any

from google.adk.events import Event
from google.genai import types


def get_long_running_function_call(event: Event) -> types.FunctionCall | None:
    """
    Extract the long-running function call from an event.
    
    Searches event parts for a function call whose ID matches
    one of the long-running tool IDs in the event.
    
    Args:
        event: The ADK Event to search.
        
    Returns:
        The matching FunctionCall if found, None otherwise.
    """
    if not event.long_running_tool_ids or not event.content or not event.content.parts:
        return None
    for part in event.content.parts:
        if part and part.function_call and part.function_call.id in event.long_running_tool_ids:
            return part.function_call
    return None


def get_function_response(event: Event, function_call_id: str) -> types.FunctionResponse | None:
    """
    Get the function response for a specific function call ID.
    
    Searches event parts for a function response matching the given ID.
    
    Args:
        event: The ADK Event to search.
        function_call_id: The ID of the function call to match.
        
    Returns:
        The matching FunctionResponse if found, None otherwise.
    """
    if not event.content or not event.content.parts:
        return None
    for part in event.content.parts:
        if part and part.function_response and part.function_response.id == function_call_id:
            return part.function_response
    return None


def extract_meme_spec(event: Event) -> dict[str, Any] | None:
    """
    Extract meme specification from MemeCreator output.
    
    Parses JSON from the MemeCreator agent's text output,
    handling markdown code blocks.
    
    Args:
        event: The event from MemeCreator agent.
        
    Returns:
        Parsed meme spec dict if successful, None otherwise.
    """
    if not hasattr(event, 'author') or event.author != 'MemeCreator':
        return None
    
    if not hasattr(event, 'content') or not event.content:
        return None
        
    for part in event.content.parts:
        if hasattr(part, 'text') and part.text:
            try:
                text = part.text.strip()
                # Remove markdown code block wrappers
                if text.startswith('```json'):
                    text = text[7:]
                if text.startswith('```'):
                    text = text[3:]
                if text.endswith('```'):
                    text = text[:-3]
                return json.loads(text.strip())
            except (json.JSONDecodeError, Exception):
                pass
    return None


def extract_meme_url(event: Event) -> str | None:
    """
    Extract meme URL from generate_imgflip_meme function response.
    
    Searches for successful Imgflip API responses in the event.
    
    Args:
        event: The ADK Event to search.
        
    Returns:
        The meme URL if found, None otherwise.
    """
    if not hasattr(event, 'content') or not event.content:
        return None
        
    for part in event.content.parts:
        if hasattr(part, 'function_response') and part.function_response:
            if part.function_response.name == 'generate_imgflip_meme':
                resp = part.function_response.response
                if resp and resp.get('success') and resp.get('url'):
                    return resp['url']
    return None

