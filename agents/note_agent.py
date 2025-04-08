import logging
from typing import Annotated
from pydantic import Field
from livekit.plugins import openai # Or cartesia, etc.

from .base import BaseAgent, RunContext_T, function_tool

# Placeholder for voice ID
# voice_id = "your_note_voice_id"

logger = logging.getLogger(__name__)

class NoteAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            instructions="You handle taking and retrieving notes for the technician. Use the 'add_note' tool to save information and retrieve it when asked. Confirm the note content before saving. After handling the note, ask if they need anything else. Do not mention anything about agents, tools, or assistants in your responses. Never refer to transferring or handing over to another agent or assistant. Speak naturally as if you're the same person throughout the conversation.",
        )

    @function_tool()
    async def add_note(self, note_content: Annotated[str, Field(description="The content of the note to be saved.")], context: RunContext_T) -> str:
        """Saves a note for the technician."""
        # In a real scenario, this would likely save to a database or file associated with the user/job
        # For now, we can store it in UserData, perhaps under a 'notes' list or dict
        userdata = context.userdata
        if 'notes' not in userdata.remembered_info:
            userdata.remembered_info['notes'] = []
        userdata.remembered_info['notes'].append(note_content)
        logger.info(f"Added note: {note_content}")
        return f"Okay, I've added the note: '{note_content}'"

    # Need a way to retrieve notes as well - could be another tool or handled by LLM based on instructions

    async def on_enter(self) -> None:
        await super().on_enter()
        logger.info("NoteAgent entered. Ready for note taking.") 