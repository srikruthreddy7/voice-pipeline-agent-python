import logging
from livekit.plugins import openai # Or cartesia, etc.

from .base import BaseAgent, RunContext_T, function_tool

# Placeholder for voice ID
# voice_id = "your_diagnosis_voice_id"

logger = logging.getLogger(__name__)

class DiagnosisAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            instructions="You specialize in diagnosing HVAC issues based on provided data (like fieldpiece readings) or user descriptions. Analyze the situation and provide technical insights. When finished, ask if the user needs anything else. Do not mention anything about agents, tools, or assistants in your responses. Never refer to transferring or handing over to another agent or assistant. Speak naturally as if you're the same person throughout the conversation.",
        )

    async def on_enter(self) -> None:
        # Fieldpiece data might be passed via context or available in UserData
        await super().on_enter()
        logger.info("DiagnosisAgent entered. Analyzing HVAC situation...")
        # LLM generates diagnosis based on prompt and context

