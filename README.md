# Meme Service

A multi-agent meme generation service using the Google Agent Development Kit (ADK), and a human-in-the-loop (HITL) architecture to refine and perfect generated memes based on user feedback.

This project demonstrates a sophisticated multi-agent pipeline where specialized agents collaborate to create a meme, and a human reviewer can approve or reject the output to iteratively improve the result.

## Project Architecture

The service uses a `SequentialAgent` pipeline to orchestrate four distinct agents, each with a specific role. A human-in-the-loop gateway ensures quality control before finalizing the meme.

```
User Prompt (e.g., "Students finding math hard")
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│                   SequentialAgent Pipeline                   │
├─────────────────────────────────────────────────────────────┤
│  1. DataGatherer                    │
│     │                                                       │
│     └──➔ Calls `reddit_mcp.py` to mine Reddit for           │
│          trending templates and context                     │
│                                                              │
├─────────────────────────────────────────────────────────────┤
│  2. MemeCreator                         │
│     │                                                       │
│     └──➔ Analyzes data and plans the meme format,           │
│          choosing a template and writing the captions       │
│                                                              │
├─────────────────────────────────────────────────────────────┤
│  3. MemeGenerator         │
│     │                                                       │
│     └──➔ Uses the `generate_imgflip_meme` tool to           │
│          create the final image via the Imgflip API         │
│                                                              │
├─────────────────────────────────────────────────────────────┤
│  4. ApprovalGateway (Gemini Flash Model)                    │
│     │                                                       │
│     └──➔ Uses a `LongRunningFunctionTool` to pause          │
│          execution and ask the human for approval:          │
│            - ✅ If Approved: Exits loop, returns meme       │
│            - ❌ If Rejected: Collects feedback, updates     │
│                 iteration history, and restarts pipeline    │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
Final Approved Meme URL (e.g., https://i.imgflip.com/xxxxx.jpg)
```

## How It Works

1.  **DataGatherer**: The first agent receives the user's topic. Its job is to brainstorm related search terms and use the Reddit MCP tool to mine Reddit for relevant posts and comments. This raw data provides the cultural context for the meme.

2.  **MemeCreator**: The second agent receives the raw data. It analyzes the text to understand the sentiment, key topics, and humor. Based on this analysis, it chooses the most fitting meme template and writes the text. 

3.  **MemeGenerator**: The third agent receives the JSON specification and executes the `generate_imgflip_meme` Python function, which communicates with the Imgflip API to generate the actual meme image. 

4.  **ApprovalGateway**: The final agent in the pipeline acts as a tollbooth. It calls a `LongRunningFunctionTool` that pauses the pipeline and waits for human input (via CLI or WebSocket). If rejected, the feedback is appended to the `iteration_context` and the whole pipeline restarts, allowing the agents to learn from the rejection.

## Prerequisites

- Python 3.12+ 

## Installation & Setup

1.  **Clone the repository:**
    ```bash
    git clone <your-repo-url>
    cd meme_service
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    # Using uv (recommended)
    uv venv
    source .venv/bin/activate
    
    # OR using standard python
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install the required dependencies:**
    ```bash
    pip install -r requirements.txt
    ```



4.  **Configure Environment Variables:**

    Create a `.env` file in the root directory (or inside `meme_refiner/`):

    ```bash
    touch .env
    ```

    Fill in your actual API keys and credentials:

    ```env
    # Required for the LLM
    GEMINI_API_KEY=your_gemini_api_key
    COHERE_API_KEY=your_cohere_api_key
    
    # Imgflip Credentials (for generating the meme image)
    # Create a free account on https://imgflip.com/signup
    IMGFLIP_USERNAME=your_username
    IMGFLIP_PASSWORD=your_password
    
    # Frontend URL for CORS (if using the web UI)
    FRONTEND_URL=http://localhost:5173
    ```

## Usage


### FastAPI WebSocket Server (For Web UI)

To use the service with a frontend application, you can start the FastAPI server which exposes a WebSocket endpoint for real-time streaming and feedback.

```bash
# Navigate to the meme_refiner directory
cd meme_refiner

uvicorn main:app --host 0.0.0.0 --port 8000
```

Then, your frontend can connect to `ws://localhost:8000/ws/{client_id}` to interact with the pipeline.

