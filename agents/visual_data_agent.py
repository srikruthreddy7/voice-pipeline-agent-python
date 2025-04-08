import logging
from livekit.plugins import openai # Keep for potential future overrides if needed
from livekit import rtc
from livekit.agents.llm import ImageContent, ChatMessage

# Moved image capture functions here
from .base import BaseAgent

# Placeholder for voice ID
# voice_id = "your_visual_voice_id"

logger = logging.getLogger(__name__)

async def get_video_track(room: rtc.Room):
    """Find and return the first available remote video track in the room."""
    if not room or not room.remote_participants:
        logger.warning("Room or remote participants not available for get_video_track.")
        return None
    for participant_id, participant in room.remote_participants.items():
        for track_id, track_publication in participant.track_publications.items():
            if track_publication.track and isinstance(
                track_publication.track, rtc.RemoteVideoTrack
            ):
                logger.info(
                    f"Found video track {track_publication.track.sid} "
                    f"from participant {participant_id}"
                )
                return track_publication.track
    logger.warning("No remote video track found in the room")
    return None # Return None explicitly if not found

async def get_latest_image(room: rtc.Room):
    """Capture and return a single frame from the video track."""
    video_stream = None
    try:
        video_track = await get_video_track(room)
        if not video_track:
             logger.warning("No video track found, cannot get latest image.")
             return None # Return None if no track found

        video_stream = rtc.VideoStream(video_track)
        async for event in video_stream:
            logger.debug("Captured latest video frame")
            return event.frame # Return the first frame received
    except Exception as e:
        logger.error(f"Failed to get latest image: {e}")
        return None
    finally:
        if video_stream:
            await video_stream.aclose()

class VisualDataAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            instructions="You are specialized in analyzing visual data. An image from the technician's camera feed will be provided in the chat context. Describe what you see, focusing on HVAC components and potential issues relevant to the ongoing task. After describing, ask the user if they need further analysis. Do not mention anything about agents, tools, or assistants in your responses. Never refer to transferring or handing over to another agent or assistant. Speak naturally as if you're the same person throughout the conversation.",
        )

    async def on_enter(self) -> None:
        logger.info("VisualDataAgent entered. Attempting to capture and add image...")
        room = self.session.userdata.current_room
        if not room:
            logger.warning("Cannot capture image: Room object not found in UserData.")
            await super().on_enter() # Proceed with base class logic (sets instructions)
            # Maybe inform the user image couldn't be captured?
            await self.session.say("I couldn't access the video feed right now.")
            return

        latest_image = await get_latest_image(room)

        # Add image to context *before* calling super().on_enter()
        # so the system prompt & image are ready for the LLM call triggered by base on_enter
        if latest_image:
            logger.info("Successfully captured image, adding to context.")
            image_content = [ImageContent(image=latest_image)]
            # Add image as a user message *before* the system prompt is added by super().on_enter()
            # This might be slightly unnatural, but ensures the image is seen first.
            # Alternatively, add it *after* super().on_enter() and before generate_reply?
            # Let's try adding before super.on_enter's system message.
            new_ctx = self.chat_ctx.copy() # Create a copy
            new_ctx.add_message(role="user", content=image_content) # Modify the copy
            await self.update_chat_ctx(new_ctx) # Update agent's context
        else:
            logger.warning("Failed to capture image.")
            # Proceed without image, maybe inform user?
            # await self.session.say("I wasn't able to get the latest image from the video feed.")


        # Now call base on_enter to add instructions and trigger reply generation
        await super().on_enter()

        if not latest_image:
             await self.session.say("I wasn't able to get the latest image from the video feed, but I'm ready to help otherwise.") 