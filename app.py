import asyncio
import threading
import logging
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pydantic import BaseModel
from livekit import api
from dotenv import load_dotenv
import os
import sys
import subprocess

# Load environment variables
load_dotenv(dotenv_path=".env.local")

# Setup logging
logger = logging.getLogger("voice-agent-api")
logging.basicConfig(level=logging.INFO)

# Create a separate process for the agent instead of importing it
# This avoids the CLI command conflict
agent_process = None

# Define lifespan context for FastAPI
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start agent process on startup
    global agent_process
    logger.info("Starting LiveKit agent in a separate process...")
    
    # Use subprocess to start agent.py in a separate process
    cmd = [sys.executable, "agent.py", "dev"]
    agent_process = subprocess.Popen(
        cmd, 
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    # Start a thread to monitor and log agent output
    def log_agent_output():
        for line in agent_process.stdout:
            logger.info(f"[AGENT] {line.strip()}")
    
    threading.Thread(target=log_agent_output, daemon=True).start()
    logger.info("Agent service started in separate process")
    
    yield
    
    # Cleanup on shutdown
    if agent_process:
        logger.info("Shutting down agent process...")
        agent_process.terminate()
        try:
            agent_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            agent_process.kill()
        logger.info("Agent process stopped")

app = FastAPI(title="LiveKit Agent Dispatcher", lifespan=lifespan)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

class DispatchRequest(BaseModel):
    room_name: str
    agent_name: str = "test-agent"
    metadata: str = None

async def create_agent_dispatch(room_name: str, agent_name: str, metadata: str = None):
    try:
        lkapi = api.LiveKitAPI()
        dispatch = await lkapi.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                agent_name=agent_name, 
                room=room_name, 
                metadata=metadata or "dispatch_via_api"
            )
        )
        logger.info(f"Created dispatch for agent {agent_name} in room {room_name}")
        
        dispatches = await lkapi.agent_dispatch.list_dispatch(room_name=room_name)
        logger.info(f"There are {len(dispatches)} dispatches in {room_name}")
        
        await lkapi.aclose()
        return dispatch
    except Exception as e:
        logger.error(f"Error creating dispatch: {str(e)}")
        raise e

@app.post("/dispatch/", status_code=202)
async def dispatch_agent(request: DispatchRequest, background_tasks: BackgroundTasks):
    logger.info(f"Dispatching agent {request.agent_name} to room {request.room_name}")
    """
    Dispatch a LiveKit agent to a room
    """
    background_tasks.add_task(
        create_agent_dispatch, 
        request.room_name, 
        request.agent_name, 
        request.metadata
    )
    return {"message": f"Dispatching agent {request.agent_name} to room {request.room_name}"}

@app.post("/dispatch-sync/")
async def dispatch_agent_sync(request: DispatchRequest):
    """
    Dispatch a LiveKit agent to a room and wait for the result
    """
    result = await create_agent_dispatch(
        request.room_name, 
        request.agent_name, 
        request.metadata
    )
    return {
        "message": f"Agent {request.agent_name} dispatched to room {request.room_name}",
        "dispatch": result.id
    }

@app.get("/")
async def root():
    return {
        "message": "LiveKit Agent Dispatcher is running",
        "agent_status": "running" if agent_process and agent_process.poll() is None else "stopped"
    }

if __name__ == "__main__":
    import uvicorn
    # Use a different port to avoid conflicts
    uvicorn.run(app, host="0.0.0.0", port=8080) 