"""
Agent factory functions for the meme generation pipeline.

This module provides factory functions that create configured LLM agents
for each stage of the meme generation workflow.
"""

import os

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from config import (
    MODEL_NAME,
    TEMPERATURE,
    ANTHROPIC_MODEL,
    OPENAI_MODEL,
)

from prompts import (
    DATA_GATHERER_INSTRUCTION,
    MEME_CREATOR_INSTRUCTION,
    MEME_GENERATOR_INSTRUCTION,
    APPROVAL_GATEWAY_INSTRUCTION,
)


# Model configuration
COHERE_MODEL = "command-a-03-2025"
GEMINI_MODEL = "gemini-2.5-flash-lite"
OLLAMA_API_BASE = os.getenv("OLLAMA_API_BASE", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")


def create_data_gatherer(reddit_toolset) -> LlmAgent:
    """
    Create the DataGatherer agent.
    
    Reads from state["refined_prompt"] to support feedback-driven refinement.
    """
    return LlmAgent(
        model=LiteLlm(model=COHERE_MODEL),
        name="DataGatherer",
        instruction=DATA_GATHERER_INSTRUCTION,
        tools=[reddit_toolset],
        output_key="reddit_data"
    )


def create_meme_creator() -> LlmAgent:
    """
    Create the MemeCreator agent.
    
    Analyzes Reddit data and outputs a JSON meme specification.
    """
    return LlmAgent(
        # model=LiteLlm(model=COHERE_MODEL),
        model=LiteLlm(model=COHERE_MODEL),
        name="MemeCreator",
        instruction=MEME_CREATOR_INSTRUCTION,
        output_key="meme_spec"
    )


def create_meme_generator(tools: list) -> LlmAgent:
    """
    Create the MemeGenerator agent.
    
    Generates the actual meme using the Imgflip API.
    """
    return LlmAgent(
        model=LiteLlm(model=COHERE_MODEL),
        name="MemeGenerator",
        instruction=MEME_GENERATOR_INSTRUCTION,
        tools=tools,
        output_key="meme_url"
    )


def create_approval_gateway(approval_tool) -> LlmAgent:
    """
    Create the ApprovalGateway agent.
    
    Handles human approval flow:
    - On approval: signals to exit loop
    - On rejection: collects feedback for next iteration
    """
    return LlmAgent(
        model=LiteLlm(model=COHERE_MODEL),
        name="ApprovalGateway",
        instruction=APPROVAL_GATEWAY_INSTRUCTION,
        tools=[approval_tool],
        output_key="approval_result"
    )

