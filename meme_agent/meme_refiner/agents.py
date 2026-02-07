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
Agent factory functions for the meme generation pipeline.

This module provides factory functions that create configured LLM agents
for each stage of the meme generation workflow.
"""

import os

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

from meme_agent.meme_refiner.prompts import (
    DATA_GATHERER_INSTRUCTION,
    MEME_CREATOR_INSTRUCTION,
    MEME_GENERATOR_INSTRUCTION,
)


# Model configuration
COHERE_MODEL = "command-a-03-2025"
GEMINI_MODEL = "gemini-2.5-flash-lite"
OLLAMA_API_BASE = os.getenv("OLLAMA_API_BASE", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")


def create_data_gatherer(reddit_toolset) -> LlmAgent:
    """
    Create the DataGatherer agent.
    
    This agent gathers Reddit content based on user topics.
    
    Args:
        reddit_toolset: MCP toolset for Reddit mining.
        
    Returns:
        Configured LlmAgent for data gathering.
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
    
    This agent analyzes Reddit data and outputs a JSON meme specification.
    
    Returns:
        Configured LlmAgent for meme creation.
    """
    return LlmAgent(
        model=LiteLlm(model=COHERE_MODEL),
        name="MemeCreator",
        instruction=MEME_CREATOR_INSTRUCTION,
        output_key="meme_spec"
    )


def create_meme_generator(imgflip_toolset) -> LlmAgent:
    """
    Create the MemeGenerator agent.
    
    This agent generates the actual meme using the Imgflip API.
    
    Args:
        imgflip_toolset: MCP toolset for Imgflip meme generation.
        
    Returns:
        Configured LlmAgent for meme generation.
    """
    return LlmAgent(
        model=LiteLlm(model=COHERE_MODEL),
        name="MemeGenerator",
        instruction=MEME_GENERATOR_INSTRUCTION,
        tools=[imgflip_toolset],
        output_key="meme_url"
    )
