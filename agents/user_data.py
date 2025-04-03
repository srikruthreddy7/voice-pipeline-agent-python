import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

from livekit.agents import llm
from livekit.agents.voice import Agent
import yaml

logger = logging.getLogger(__name__)

@dataclass
class UserData:
    # Store any user-related data here
    remembered_info: Dict[str, Any] = field(default_factory=dict)

    agents: dict[str, Agent] = field(default_factory=dict)
    prev_agent: Optional[Agent] = None
    current_room: Optional[Any] = None # To store the room object for image capture etc.


    def summarize(self) -> str:
        # Adapt summary as needed
        data = {
            "remembered_info": self.remembered_info or "empty",
        }
        # summarize in yaml performs better than json
        try:
            return yaml.dump(data)
        except Exception as e:
            logger.error(f"Error summarizing user data: {e}")
            return str(data) # Fallback to string representation 