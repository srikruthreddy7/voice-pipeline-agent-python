import logging
from livekit.plugins import openai # Or cartesia, etc.

from .base import BaseAgent, RunContext_T, function_tool

# Placeholder for voice ID
# voice_id = "your_workflow_voice_id"

logger = logging.getLogger(__name__)

class WorkflowAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            instructions="You guide technicians through HVAC workflows step-by-step. Retrieve existing workflows or create new ones as needed. Confirm the workflow with the user before starting. After completing or exiting a workflow, ask if they need another workflow or want to return to the main assistant.",
            # LLM and TTS are inherited from AgentSession
            # Add tools specific to workflow management (e.g., retrieve_workflow, create_workflow, next_step)
        )

    async def on_enter(self) -> None:
        await super().on_enter()
        logger.info("WorkflowAgent entered. Ready to manage workflows.")
        # Initial prompt might ask which workflow the user wants 