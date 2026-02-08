# Meme Refiner Pipeline

A modular meme generation pipeline with human-in-the-loop validation, iterative feedback refinement, and multi-agent orchestration built on Google ADK.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                     MEME GENERATION PIPELINE                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   ┌──────────────┐    ┌──────────────┐    ┌───────────────────┐    │
│   │ DataGatherer │───▶│ MemeCreator  │───▶│  MemeGenerator    │    │
│   │              │    │              │    │                   │    │
│   │ Reddit MCP   │    │ JSON Spec    │    │ Imgflip API       │    │
│   └──────────────┘    └──────────────┘    └─────────┬─────────┘    │
│                                                     │               │
│                                                     ▼               │
│                                         ┌───────────────────┐       │
│                                         │ ApprovalGateway   │       │
│                                         │                   │       │
│                                         │ Human Validation  │       │
│                                         └─────────┬─────────┘       │
│                                                   │                 │
│                              ┌────────────────────┴────────────┐    │
│                              ▼                                 ▼    │
│                        ┌──────────┐                     ┌──────────┐│
│                        │ APPROVED │                     │ REJECTED ││
│                        │   Exit   │                     │  Retry   ││
│                        └──────────┘                     └──────────┘│
│                                                               │     │
│                                              Feedback Loop ◀──┘     │
└─────────────────────────────────────────────────────────────────────┘
```

## Modules

| Module | Purpose |
|--------|---------|
| `pipeline.py` | Main orchestration logic with retry loop |
| `agents.py` | Agent factory functions for all 4 pipeline stages |
| `prompts.py` | LLM instruction templates for each agent |
| `config.py` | Centralized configuration and constants |
| `tools.py` | `ask_approval` long-running function for human validation |
| `logging_utils.py` | Event logging with Rich console formatting |
| `event_handlers.py` | ADK event extraction utilities |
| `utils.py` | Imgflip API integration |
| `refinement.py` | CLI entry point |

## Installation

```bash
# Clone and navigate to the repository
cd meme_service

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Environment Variables

Create a `.env` file in the project root:

```env
# Required - Imgflip API
IMGFLIP_USERNAME=your_username
IMGFLIP_PASSWORD=your_password

# Optional - Database persistence (defaults to in-memory)
DATABASE_URL=postgresql+asyncpg://user:pass@host:port/dbname

COHERE_API_KEY=your_cohere_key
GOOGLE_API_KEY=your_google_key
```

## Usage

### CLI

```bash
# Run with a topic
python meme_agent/meme_refiner/refinement.py "monday morning struggles"



## Pipeline Stages

### 1. DataGatherer
Searches Reddit for relevant content using the MCP Reddit server.

**Input**: User topic (e.g., "monday morning struggles")  
**Output**: Reddit posts and comments as context

### 2. MemeCreator
Analyzes Reddit data and generates a JSON meme specification.

**Input**: Reddit context data  
**Output**: JSON with template_id, top_text, bottom_text

**Template Selection**: Uses a catalog of 20+ meme templates matched to emotional tone:
- Chaos/fire → "This Is Fine"
- Avoidance → "Uno Draw 25"
- Confusion → "Is This A Pigeon"
- Comparison → "Drake Hotline Bling"

### 3. MemeGenerator
Calls the Imgflip API to generate the actual meme image.

**Input**: Meme specification JSON  
**Output**: Generated meme URL

### 4. ApprovalGateway
Pauses for human review using `LongRunningFunctionTool`.

**Input**: Meme URL  
**Output**: APPROVED or REJECTED with feedback

## Iteration Context

The pipeline maintains structured iteration history:

```json
{
  "initial_prompt": "monday morning struggles",
  "iterations": [
    {
      "iteration": 1,
      "meme_spec": {
        "template_id": 55311130,
        "template_name": "This Is Fine",
        "top_text": "...",
        "bottom_text": "..."
      },
      "meme_url": "https://i.imgflip.com/xxx.jpg",
      "human_feedback": "make it funnier"
    }
  ]
}
```

On rejection, feedback is appended and agents receive full context to avoid repeating mistakes.

## Configuration

Edit `config.py` to customize:

```python
MAX_ITERATIONS = 5      # Max retry attempts
COHERE_MODEL = "command-a-03-2025"
GEMINI_MODEL = "gemini-2.5-flash"
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `IMGFLIP credentials not set` | Set `IMGFLIP_USERNAME` and `IMGFLIP_PASSWORD` in `.env` |
| Database connection slow | Use `DATABASE_URL=""` to use in-memory session |
| DataGatherer only passes 1 topic | Ensure prompts.py has the "EXPAND THE TOPIC" instruction |
| MCP connection fails | Check reddit_mcp.py has `duckduckgo_search` installed |

## License

Apache 2.0
