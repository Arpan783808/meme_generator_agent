
"""
Configuration constants for the meme generation pipeline.

This module centralizes all configuration values including model names,
environment variables, and pipeline settings.
"""

import os

from dotenv import load_dotenv

load_dotenv()

# Model Configuration
COHERE_MODEL = "command-a-03-2025"
GEMINI_MODEL = "gemini-2.5-flash"

# Pipeline Settings
MAX_ITERATIONS = 5
USER_ID = "user1"

# Database Configuration
_raw_db_url = os.getenv("DATABASE_URL", "")
DB_URL = _raw_db_url.replace("postgresql://", "postgresql+asyncpg://") if _raw_db_url else None

# Imgflip Credentials
IMGFLIP_USERNAME = os.getenv("IMGFLIP_USERNAME", "")
IMGFLIP_PASSWORD = os.getenv("IMGFLIP_PASSWORD", "")
