import logging
import os
import httpx
import tempfile  # Add tempfile module to read the metadata file
import json

from dotenv import load_dotenv
from livekit.agents import (
    AutoSubscribe,
    JobContext,
    JobProcess,
    WorkerOptions,
    WorkerType,
    cli,
    llm,
    metrics,
)
from livekit.agents.llm import function_tool
from livekit.agents.voice import  AgentSession, room_io
from livekit.plugins import (
    cartesia,
    openai,
    deepgram,
    noise_cancellation,
    silero,
    turn_detector,
)
from livekit.plugins.openai import stt, tts
from livekit import rtc
from livekit.agents.voice.room_io import RoomInputOptions
from datetime import datetime
# Import the new agent structure
from agents.user_data import UserData
from agents.main_agent import MainAgent
from agents.visual_data_agent import VisualDataAgent
from agents.diagnosis_agent import DiagnosisAgent
from agents.workflow_agent import WorkflowAgent
from agents.note_agent import NoteAgent


load_dotenv(dotenv_path=".env.local")
logger = logging.getLogger("voice-agent")


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()
    logger.info("VAD model prewarmed.")


async def entrypoint(ctx: JobContext):
    logger.info(f"connecting to room {ctx.room.name}")
    
    # Add extensive logging about the JobContext
    logger.info(f"JobContext details:")
    logger.info(f"  Room: {ctx.room.name}")
    logger.info(f"  Job: {ctx.job}")
    logger.info(f"  Job ID: {ctx.job.id if ctx.job else 'None'}")
    logger.info(f"  Job metadata: {ctx.job.metadata if ctx.job else 'None'}")
    logger.info(f"  Job metadata type: {type(ctx.job.metadata) if ctx.job and ctx.job.metadata else 'None'}")
    logger.info(f"  Job agent_name: {ctx.job.agent_name if ctx.job else 'None'}")
    logger.info(f"  Job dispatch_id: {ctx.job.dispatch_id if ctx.job else 'None'}")
    
    # Log all attributes of JobContext for debugging
    logger.info(f"All JobContext attributes: {dir(ctx)}")
    logger.info(f"All Job attributes: {dir(ctx.job) if ctx.job else 'None'}")

    # Initialize agent first so the shutdown callback can access it
    userdata = UserData(current_room=ctx.room)
    
    # Try to read metadata from file if job metadata is empty
    metadata_from_file = None
    try:
        metadata_dir = os.path.join(tempfile.gettempdir(), "voice_agent_metadata")
        metadata_file = os.path.join(metadata_dir, f"{ctx.room.name}.json")
        
        if os.path.exists(metadata_file):
            logger.info(f"Found metadata file: {metadata_file}")
            with open(metadata_file, 'r') as f:
                metadata_from_file = f.read()
            logger.info(f"Read metadata from file: {metadata_from_file}")
    except Exception as e:
        logger.error(f"Error reading metadata from file: {e}")
    
    # Attempt to retrieve metadata from dispatch if not present in job
    metadata_from_dispatch = None
    if ctx.job and not ctx.job.metadata and ctx.job.dispatch_id:
        try:
            logger.info(f"Job metadata missing. Attempting to fetch from dispatch_id: {ctx.job.dispatch_id}")
            # Create LiveKit API client to fetch dispatch info
            from livekit import api
            lkapi = api.LiveKitAPI()
            
            # Fetch dispatch info directly
            dispatches = await lkapi.agent_dispatch.list_dispatch(room_name=ctx.room.name)
            for d in dispatches:
                logger.info(f"Found dispatch: ID={d.id}, metadata={d.metadata}")
                if d.id == ctx.job.dispatch_id:
                    metadata_from_dispatch = d.metadata
                    logger.info(f"Found metadata from dispatch: {metadata_from_dispatch}")
                    break
            
            if metadata_from_dispatch:
                logger.info(f"Successfully retrieved metadata from dispatch: {metadata_from_dispatch}")
            else:
                logger.warning(f"Could not find dispatch with ID: {ctx.job.dispatch_id}")
                
            await lkapi.aclose()
        except Exception as e:
            logger.error(f"Error fetching dispatch metadata: {e}")
    
    # Use metadata in this order of preference:
    # 1. Job metadata (if available)
    # 2. Metadata from file (our direct method)
    # 3. Metadata from dispatch (backup method)
    # 4. None
    if ctx.job and ctx.job.metadata:
        logger.info(f"Using metadata from job: {ctx.job.metadata}")
        userdata.job_metadata = ctx.job.metadata
    elif metadata_from_file:
        logger.info(f"Using metadata from file: {metadata_from_file}")
        userdata.job_metadata = metadata_from_file
    elif metadata_from_dispatch:
        logger.info(f"Using metadata from dispatch: {metadata_from_dispatch}")
        userdata.job_metadata = metadata_from_dispatch
    else:
        logger.warning("No metadata available from any source")
        userdata.job_metadata = None
    
    logger.info(f"Final metadata stored in UserData: {userdata.job_metadata}")
    
    main_agent = MainAgent()
    visual_agent = VisualDataAgent()
    diagnosis_agent = DiagnosisAgent()
    workflow_agent = WorkflowAgent()
    note_agent = NoteAgent()

    userdata.agents = {
        "main": main_agent,
        "visual": visual_agent,
        "diagnosis": diagnosis_agent,
        "workflow": workflow_agent,
        "note": note_agent,
    }

    agent = AgentSession[UserData](
        userdata=userdata,
        vad=silero.VAD.load(),
        stt=openai.STT(language="en", model="gpt-4o-transcribe", prompt="You are a helpful assistant that can answer questions and help with tasks related to HVAC systems. You are an voice ai HVAC diagnostic assistant speaking to an hvac technician on a job site."), # Apply STT config here
        llm=openai.LLM(model="gpt-4o"),
        tts=openai.TTS(model="gpt-4o-mini-tts", voice="ash"),   # Apply TTS config here
        turn_detection=turn_detector.EOUModel(),
        min_endpointing_delay=0.5,
        max_endpointing_delay=5.0,
        
    )

    # Define the shutdown callback *after* agent is defined so it can capture it
    async def send_transcript_on_shutdown():
        server_url = os.getenv("AITAS_SERVER_URL")
        if not server_url:
            logger.error("AITAS_SERVER_URL not set. Cannot send transcript.")
            return

        endpoint = f"{server_url.rstrip('/')}/v2/generate-report"
        transcript_data = agent.history.to_dict()
        room_name = ctx.room.name # Get room name from context
        payload = {
            "transcript": transcript_data,
            "sessionId": room_name # Add session ID (room name)
        }
        
        logger.info(f"Sending transcript to {endpoint}")
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    endpoint,
                    json=payload, # Use json parameter for automatic serialization and header
                    timeout=20.0 
                )
                response.raise_for_status() # Check for HTTP errors
                logger.info(f"Transcript successfully sent to {endpoint}. Status: {response.status_code}")
        except httpx.RequestError as e:
            logger.error(f"Error sending transcript to {endpoint}: {e}")
        except Exception as e:
            logger.error(f"An unexpected error occurred while sending transcript: {e}")

    ctx.add_shutdown_callback(send_transcript_on_shutdown)

    await ctx.connect(auto_subscribe=AutoSubscribe.SUBSCRIBE_ALL)
    logger.info(f"Connected to room {ctx.room.name}")

    usage_collector = metrics.UsageCollector()

    @agent.on("metrics_collected")
    def on_metrics_collected(agent_metrics: metrics.AgentMetrics):
        metrics.log_metrics(agent_metrics)
        usage_collector.collect(agent_metrics)

    logger.info(f"Starting AgentSession with MainAgent for room {ctx.room.name}")
    await agent.start(
        agent=main_agent,
        room=ctx.room,
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    # Add the initial greeting with the user's name using the simplified method
    user_name = userdata.get_user_name()  # This safely handles all parsing and error cases
    logger.info(f"Greeting user with name: {user_name}")
    await agent.say(f"Hey {user_name}, is the system running or not?", allow_interruptions=True)

    logger.info("AgentSession started and listening.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.info("Starting agent worker...")
    opts= WorkerOptions(
        entrypoint_fnc=entrypoint,
        prewarm_fnc=prewarm,
        worker_type=WorkerType.ROOM,
    )
    cli.run_app(opts)
    
