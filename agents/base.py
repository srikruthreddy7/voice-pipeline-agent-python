import logging
from typing import TypeVar

from livekit.agents import llm
from livekit.agents.llm import function_tool
from livekit.agents.voice import Agent, RunContext

# Import *our* UserData definition
from .user_data import UserData

logger = logging.getLogger(__name__)

# Define the RunContext type specific to our UserData
RunContext_T = RunContext[UserData]

class BaseAgent(Agent):
    """Base class for all agents in this application.

    This class serves as a common ancestor and can be expanded later
    with shared functionalities like context management or agent transitions.
    For now, it provides a minimal structure.
    """

    def __init__(self, **kwargs):
        # Pass any arguments needed by the parent Agent class
        super().__init__(**kwargs)
        logger.debug(f"BaseAgent initialized for {self.__class__.__name__}")

    # Add common methods or properties here later as needed.
    # For example:
    # async def common_setup(self):
    #     pass

    async def on_enter(self) -> None:
        """Common logic executed when an agent becomes active."""
        agent_name = self.__class__.__name__
        logger.info(f"Entering task: {agent_name}")

        userdata: UserData = self.session.userdata
        chat_ctx = self.chat_ctx.copy()

        # Add the previous agent's chat history to the current agent
        # Check if prev_agent and its chat_ctx exist
        if userdata.prev_agent and hasattr(userdata.prev_agent, 'chat_ctx') and userdata.prev_agent.chat_ctx:
            # Get the full history from the previous agent
            items_copy = list(userdata.prev_agent.chat_ctx.items)

            # Filter out items already present in the current context (by ID)
            existing_ids = {item.id for item in chat_ctx.items if hasattr(item, 'id') and item.id}
            items_copy = [item for item in items_copy if hasattr(item, 'id') and item.id not in existing_ids]
            
            # Extend with the full, filtered history
            chat_ctx.items.extend(items_copy)
            logger.debug(f"Extended chat context with {len(items_copy)} items from {userdata.prev_agent.__class__.__name__} (NO TRUNCATION)")
        else:
            logger.debug("No previous agent context to extend.")

        # Add instructions including the summarized user data as a system message
        # Ensure userdata.summarize() method exists and works
        try:
            user_summary = userdata.summarize()
        except Exception as e:
            logger.error(f"Error summarizing user data: {e}")
            user_summary = "(Could not summarize user data)"

        chat_ctx.add_message(
            role="system",
            content=f"You are the {agent_name}. Current user data: \n{user_summary}",
        )

        await self.update_chat_ctx(chat_ctx)
        
        # Remove the automatic reply generation on entry
        # Let the explicit agent.say or user interaction trigger replies
        # self.session.generate_reply(tool_choice="auto") 
        
        logger.debug(f"{agent_name} entered, context updated.") # Updated log message

    async def _transfer_to_agent(self, name: str, context: RunContext_T) -> tuple[Agent, str]:
        """Handles the logic for transferring control to another agent."""
        userdata = context.userdata
        current_agent = context.session.current_agent
        agent_name = current_agent.__class__.__name__ if current_agent else "UnknownAgent"

        if name not in userdata.agents:
            logger.error(f"Agent '{name}' not found in userdata.agents keys: {list(userdata.agents.keys())}")
            # Stay in the current agent and inform the user
            return current_agent, f"Sorry, I encountered an issue and cannot transfer to {name} right now."

        next_agent = userdata.agents[name]
        userdata.prev_agent = current_agent # Store the *instance* of the current agent

        logger.info(f"Transferring from {agent_name} to {name}")
        # Generic transition message that doesn't mention agents or assistants
        if name == "main":
            return next_agent, "Alright, I understand. Let's get back to our conversation."
        else:
            return next_agent, "Okay, I can help you with that."

    def _truncate_chat_ctx(
        self,
        items: list[llm.ChatItem],
        keep_last_n_messages: int = 6,
        keep_system_message: bool = False,
        keep_function_call: bool = False,
    ) -> list[llm.ChatItem]:
        """Truncates the chat context to keep recent messages, configurable."""
        if not items:
            return []

        def _valid_item(item: llm.ChatItem) -> bool:
            if not hasattr(item, 'type'): return False # Basic safety check

            if not keep_system_message and item.type == "message" and hasattr(item, 'role') and item.role == "system":
                return False
            # Allow keeping function calls/outputs if needed for context
            if not keep_function_call and item.type in ["function_call", "function_call_output"]:
                return False
            return True

        new_items: list[llm.ChatItem] = []
        count = 0
        for item in reversed(items):
            if _valid_item(item):
                new_items.append(item)
                count += 1 # Only count valid items towards the limit
            if count >= keep_last_n_messages:
                break

        new_items = new_items[::-1] # Reverse back to chronological order

        # Ensure the truncated list doesn't start with orphaned function results
        while new_items and hasattr(new_items[0], 'type') and new_items[0].type == "function_call_output":
            logger.debug("Removing leading function_call_output from truncated context.")
            new_items.pop(0)
        # Maybe also remove leading function_call if its output is gone?
        # while new_items and hasattr(new_items[0], 'type') and new_items[0].type == "function_call":
        #    new_items.pop(0)

        logger.debug(f"Truncated context to {len(new_items)} items (kept last {keep_last_n_messages}, keep_system={keep_system_message}, keep_func={keep_function_call})")
        return new_items

    # This tool should be included in the 'tools' list of specialist agents
    # It allows them to hand control back to the MainAgent
    @function_tool()
    async def to_main(self, context: RunContext_T) -> tuple[Agent, str]:
        """Called when the current specialized task is complete or the user wants to return to the main assistant."""
        return await self._transfer_to_agent("main", context)