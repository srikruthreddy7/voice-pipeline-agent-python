import logging
import os
import httpx

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
import json
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

    # Initialize agent first so the shutdown callback can access it
    userdata = UserData(current_room=ctx.room)
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
        stt=openai.STT(language="en", model="gpt-4o-transcribe"), # Apply STT config here
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

    # Add the initial greeting back to ensure the first TTS call is valid
    await agent.say("Hey, how can I help you today?", allow_interruptions=True)

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
    
