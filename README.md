# Meme Service

A multi-agent meme generation service using the Google Agent Development Kit (ADK), LiteLLM, and custom MCP servers to create memes based on user topics.

This project demonstrates a sophisticated multi-agent pipeline where specialized agents collaborate to turn a simple idea into a finished meme.

## Project Architecture

The service uses a `SequentialAgent` pipeline to orchestrate three distinct agents, each with a specific role. This separation of concerns allows for a more robust and maintainable system.

```
User Prompt (e.g., "AI taking over jobs")
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│                   SequentialAgent Pipeline                   │
├─────────────────────────────────────────────────────────────┤
│  1. DataGatherer (Cohere Model)                             │
│     │                                                       │
│     └──➔ Calls `mine_reddit_context` tool via MCP           │
│          (meme_agent/reddit_mcp.py)                         │
│     │                                                       │
│     └──➔ Output: Scraped Reddit content ({reddit_data})     │
│                                                              │
├─────────────────────────────────────────────────────────────┤
│  2. MemeCreator (Cohere Model)                              │
│     │                                                       │
│     └──➔ Input: {reddit_data}                               │
│     │                                                       │
│     └──➔ Output: JSON meme specification ({meme_spec})      │
│                                                              │
├─────────────────────────────────────────────────────────────┤
│  3. MemeGenerator (Cohere Model)                            │
│     │                                                       │
│     └──➔ Calls `generate_meme` tool via MCP                 │
│          (meme_agent/imgflip_mcp.py)                        │
│     │                                                       │
│     └──➔ Input: {meme_spec}                                 │
│     │                                                       │
│     └──➔ Output: Final meme URL                             │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
Final Meme URL (e.g., https://i.imgflip.com/xxxxx.jpg)
```

## How It Works

1.  **DataGatherer**: The first agent receives the user's topic. Its job is to brainstorm related search terms and use the custom `reddit_mcp.py` tool to mine Reddit for relevant posts and comments. This raw data provides the context for the meme.

2.  **MemeCreator**: The second agent receives the raw data from the `DataGatherer`. It analyzes the text to understand the sentiment, key topics, and humor. Based on this analysis, it chooses the most fitting meme template from a predefined list and writes the top and bottom text. Its final output is a structured JSON object.

    *Example `meme_spec` JSON:*
    ```json
    {
        "meme_template_id": 181913649,
        "template_name": "Drake Hotline Bling",
        "top_text": "Writing code from scratch",
        "bottom_text": "Googling for code snippets"
    }
    ```

3.  **MemeGenerator**: The final agent in the pipeline receives the JSON specification. Its sole purpose is to call the `imgflip_mcp.py` tool, which communicates with the Imgflip API to generate the meme image. It then outputs the final URL.

## Prerequisites

- Python 3.9+
- An active internet connection

## Installation & Setup

1.  **Clone the repository:**
    ```bash
    git clone <your-repo-url>
    cd meme_service
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install the required dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure Environment Variables:**

    You will need to provide API keys for the services used in this project.
    Copy the example environment file and rename it to `.env` inside the `meme_agent/` directory:

    ```bash
    cp meme_agent/.env.example meme_agent/.env
    ```

    Then, open `meme_agent/.env` and fill in your actual API keys and credentials.

    - **Cohere/Google API Key**: Obtain this from the [AI Studio dashboard](https://aistudio.google.com/app/apikey).
    - **Imgflip Credentials**: Create a free account on [imgflip.com](https://imgflip.com/signup).

## Usage

You can run the entire meme generation pipeline from your command line.

```bash
# Navigate to the project root
cd /path/to/meme_service

# Run the agent with your desired meme topic
python3 meme_agent/agent.py "A funny meme about programmers and coffee"
```

The agent will print its progress, including which agent is running and which tools are being called. The final output will be the URL to the generated meme.

## Project Structure

```
meme_service/
├── meme_agent/
│   ├── __init__.py         # Package initialization
│   ├── agent.py            # Main agent orchestration logic (SequentialAgent)
│   ├── reddit_mcp.py       # MCP server for mining Reddit content
│   ├── imgflip_mcp.py      # MCP server for generating memes via Imgflip API
│   └── .env.example        # Example environment file
├── requirements.txt        # Python dependencies
└── README.md               # This file
```