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
import json
import tempfile  # Add tempfile module for creating a metadata file

# Load environment variables
load_dotenv(dotenv_path=".env.local")

# Setup logging - FIX LOGGING CONFIGURATION
# Configure the root logger first
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Get a named logger and ensure it propagates to root
logger = logging.getLogger("voice-agent-api")
logger.setLevel(logging.INFO)

# Add a specific handler if needed
if not logger.handlers:
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(console_handler)

# Log a test message to confirm logger is working
logger.info("Starting voice-agent-api with fixed logging configuration")

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
        try:
            logger.info("Agent log monitor thread started")
            for line in agent_process.stdout:
                if line.strip():  # Skip empty lines
                    logger.info(f"[AGENT] {line.strip()}")
            logger.info("Agent log monitor thread ending (no more output)")
        except Exception as e:
            logger.error(f"Error in agent log monitor thread: {e}")
    
    agent_log_thread = threading.Thread(target=log_agent_output, daemon=True)
    agent_log_thread.start()
    logger.info("Agent service started in separate process with log monitoring")
    
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

# Add a function to write metadata to a file that the agent can read
def write_metadata_to_file(room_name, metadata):
    """Write metadata to a file for the agent to read"""
    try:
        metadata_dir = os.path.join(tempfile.gettempdir(), "voice_agent_metadata")
        os.makedirs(metadata_dir, exist_ok=True)
        
        metadata_file = os.path.join(metadata_dir, f"{room_name}.json")
        
        with open(metadata_file, 'w') as f:
            f.write(metadata)
            
        logger.info(f"Wrote metadata to file: {metadata_file}")
        print(f"DIRECT PRINT - Wrote metadata to file: {metadata_file}")
        return metadata_file
    except Exception as e:
        logger.error(f"Error writing metadata to file: {e}")
        print(f"DIRECT PRINT - Error writing metadata to file: {e}")
        return None

async def create_agent_dispatch(room_name: str, agent_name: str, metadata: str = None):
    try:
        # Direct print for debugging
        print(f"DIRECT PRINT - create_agent_dispatch called with metadata: {metadata}")
        
        logger.info("=" * 40)
        logger.info("CREATING AGENT DISPATCH")
        logger.info(f"Room: {room_name}")
        logger.info(f"Agent: {agent_name}")
        logger.info(f"Original metadata: {metadata}")
        
        # Initialize the LiveKit API client
        lkapi = api.LiveKitAPI()
        
        # Process metadata to ensure it's in the right format
        processed_metadata = None
        if metadata:
            try:
                # If it's already a JSON string, we'll parse and then re-stringify to ensure proper format
                parsed_data = json.loads(metadata)
                logger.info(f"Parsed metadata JSON successfully: {parsed_data}")
                print(f"DIRECT PRINT - Parsed metadata: {parsed_data}")
                
                # Convert back to string for LiveKit
                processed_metadata = json.dumps(parsed_data)
                logger.info(f"Re-serialized metadata: {processed_metadata}")
                
                # Write metadata to file for agent to read
                metadata_file = write_metadata_to_file(room_name, processed_metadata)
                logger.info(f"Metadata saved to file for agent to read: {metadata_file}")
                
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse metadata as JSON: {metadata}. Error: {e}")
                print(f"DIRECT PRINT - JSON decode error: {e}")
                processed_metadata = metadata  # Use as-is if not valid JSON
                
                # Still try to write it to a file
                metadata_file = write_metadata_to_file(room_name, metadata)
        
        # Ensure we always have at least some metadata
        if not processed_metadata:
            # Create a default metadata object as a fallback
            default_metadata = json.dumps({
                "sessionDOName": "Test User",
                "companyId": "default-company",
                "source": "api-fallback"
            })
            logger.info(f"Using default metadata: {default_metadata}")
            print(f"DIRECT PRINT - Using default metadata: {default_metadata}")
            processed_metadata = default_metadata
            
        # Create the request with very explicit parameters
        logger.info(f"Creating dispatch request with metadata: {processed_metadata}")
        print(f"DIRECT PRINT - Creating dispatch request with metadata: {processed_metadata}")
        
        # Log the final request object
        logger.info("Dispatch request created.")
        print(f"DIRECT PRINT - Request: {processed_metadata}")
        
        # Log all arguments being used
        print(f"DIRECT PRINT - Dispatch arguments:")
        print(f"  - agent_name: {agent_name}")
        print(f"  - room_name: {room_name}")
        print(f"  - metadata: {processed_metadata}")
        
        # Use keyword arguments as required by the API
        request = api.CreateAgentDispatchRequest(
            agent_name=agent_name, 
            room=room_name,
            metadata=processed_metadata
        )
        
        # Log the final request object after recreation
        logger.info("Recreated dispatch request object with keyword arguments.")
        print(f"DIRECT PRINT - Final Request: {request}")
        
        # Create the dispatch with explicit logging
        dispatch = await lkapi.agent_dispatch.create_dispatch(request)
        logger.info(f"Created dispatch with ID: {dispatch.id}")
        
        logger.info(f"Created dispatch for agent {agent_name} in room {room_name}")
        
        dispatches = await lkapi.agent_dispatch.list_dispatch(room_name=room_name)
        logger.info(f"There are {len(dispatches)} dispatches in {room_name}")
        for d in dispatches:
            logger.info(f"  Dispatch: {d.id}, metadata: {d.metadata}")
        
        await lkapi.aclose()
        return dispatch
    except Exception as e:
        logger.error(f"Error creating dispatch: {str(e)}")
        raise e

@app.post("/dispatch", status_code=202)
async def dispatch_agent(request: DispatchRequest, background_tasks: BackgroundTasks):
    """
    Dispatch a LiveKit agent to a room
    """
    # Direct prints for debugging
    print("\n" + "=" * 60)
    print("RECEIVED DISPATCH REQUEST - DIRECT PRINT")
    print(f"Request Dict: {request.dict()}")
    print(f"Room Name: {request.room_name}")
    print(f"Agent Name: {request.agent_name}")
    print(f"Metadata: {request.metadata}")
    print(f"Metadata Type: {type(request.metadata)}")
    print("=" * 60 + "\n")
    
    # Log the full request data with clear separators
    logger.info("=" * 40)
    logger.info("RECEIVED DISPATCH REQUEST")
    logger.info(f"Room: {request.room_name}")
    logger.info(f"Agent: {request.agent_name}")
    logger.info(f"Metadata: {request.metadata}")
    logger.info(f"Metadata type: {type(request.metadata)}")
    logger.info("=" * 40)
    
    # Test direct printing to stdout as a fallback
    print(f"DIRECT PRINT - Received request: {request.dict()}")
    
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
    print("\n\n" + "=" * 50)
    print("STARTING VOICE AGENT API SERVER")
    print(f"Logging level: {logger.level}")
    print(f"Logger has handlers: {len(logger.handlers)}")
    print("=" * 50 + "\n\n")
    
    uvicorn.run(app, host="0.0.0.0", port=8080)