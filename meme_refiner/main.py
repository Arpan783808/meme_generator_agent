"""
FastAPI server for the Meme Generator Agent.

Exposes an endpoint to generate memes using the human-in-the-loop pipeline.
"""

import asyncio
import json
from typing import Dict, Any, Callable, Awaitable
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from .pipeline import create_meme
import os
from .pipeline import generate_meme

app = FastAPI(title="Meme Generator API", version="1.0.0")

# Define allowed origins
# In production, this should be the frontend URL.
# In development, it defaults to the Vite server.
origins = [
    os.getenv("FRONTEND_URL", "http://localhost:5173"),
    "http://localhost:8000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self.active_connections[client_id] = websocket

    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]

    async def send_personal_message(self, message: dict, client_id: str):
        if client_id in self.active_connections:
            await self.active_connections[client_id].send_json(message)

manager = ConnectionManager()

class FeedbackManager:
    def __init__(self):
        # Map client_id -> Future
        self.pending_feedback: Dict[str, asyncio.Future] = {}

    def create_request(self, client_id: str) -> asyncio.Future:
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self.pending_feedback[client_id] = future
        return future

    def resolve_request(self, client_id: str, data: dict):
        if client_id in self.pending_feedback:
            future = self.pending_feedback[client_id]
            if not future.done():
                future.set_result(data)
            del self.pending_feedback[client_id]

feedback_manager = FeedbackManager()

class MemeRequest(BaseModel):
    prompt: str
    client_id: str | None = None

class MemeResponse(BaseModel):
    meme_url: str | None
    result: str
    iterations: int
    approved: bool

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await manager.connect(websocket, client_id)
    try:
        while True:
            text_data = await websocket.receive_text()
            try:
                data = json.loads(text_data)
                
                # Check if this is a feedback decision
                if data.get("type") == "decision":
                    feedback_manager.resolve_request(client_id, data)
                else:
                    # Echo for verification/keepalive
                    await manager.send_personal_message({"type": "echo", "data": data}, client_id)
            except json.JSONDecodeError as e:
                print(f"❌ JSON Decode Error for client {client_id}: {e}")
                print(f"   Received text: {text_data}")
                
    except WebSocketDisconnect:
        manager.disconnect(client_id)

async def _feedback_handler(client_id: str, payload: dict) -> dict:
    """
    Async callback injected into the pipeline.
    Sends meme info/events to WS.
    If it's an event_log, it returns immediately.
    If it's an approval_request, it waits for feedback.
    """
    msg_type = payload.get("type", "approval_request")

    # 1. Send message to client
    await manager.send_personal_message(payload, client_id)
    
    # 2. If it's just a log, return immediately
    if msg_type == "event_log":
        return {}
    
    # 3. If approval needed, wait for feedback
    print(f"Waiting for feedback from {client_id}...")
    future = feedback_manager.create_request(client_id)
    result = await future
    print(f"Received feedback from {client_id}: {result}")
    
    return result

@app.post("/generate-meme", response_model=MemeResponse)
async def generate_meme_endpoint(request: MemeRequest):
    """
    Generate a meme based on the provided prompt.
    """
    try:
        if not request.client_id or request.client_id not in manager.active_connections:
            raise HTTPException(status_code=400, detail="Client must be connected via WebSocket first.")

        async def bound_handler(payload: dict) -> dict:
            return await _feedback_handler(request.client_id, payload)

        from .pipeline import generate_meme
        result = await generate_meme(request.prompt, feedback_handler=bound_handler)
        
        return MemeResponse(
            meme_url=result.get("meme_url"),
            result=result.get("result", ""),
            iterations=result.get("iterations", 0),
            approved=result.get("approved", False)
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
