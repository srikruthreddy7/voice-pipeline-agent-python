import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

from livekit.agents import llm
from livekit.agents.voice import Agent
import yaml
import json

logger = logging.getLogger(__name__)

@dataclass
class UserData:
    """Data structure for persistent user data between agents."""

    def __init__(self, current_room=None):
        # Room reference for room operations
        self.current_room = current_room
        # Dictionary of agent instances
        self.agents = {}  
        # Dictionary for storing remembered information
        self.remembered_info = {}
        # Store job metadata from the JobContext
        self.job_metadata = None
        # Cached processed metadata
        self._processed_metadata = None

    # Store any user-related data here
    remembered_info: Dict[str, Any] = field(default_factory=dict)

    agents: dict[str, Agent] = field(default_factory=dict)
    prev_agent: Optional[Agent] = None
    current_room: Optional[Any] = None # To store the room object for image capture etc.

    # Store job metadata from the JobContext
    job_metadata: Optional[str] = None
    
    @property
    def processed_metadata(self) -> Optional[Dict[str, Any]]:
        """
        Returns the processed metadata dictionary. 
        Parses JSON string once and caches the result for future access.
        Handles potential double-encoded JSON strings from the client.
        """
        # Return cached value if available
        if self._processed_metadata is not None:
            return self._processed_metadata
        
        # No metadata to process
        if not self.job_metadata:
            logger.warning("No job metadata available")
            return None
            
        # Empty string check
        if isinstance(self.job_metadata, str) and not self.job_metadata.strip():
            logger.warning("Job metadata is an empty string")
            return None
        
        try:
            # Log the raw metadata for debugging
            logger.info(f"Raw metadata: {self.job_metadata} (type: {type(self.job_metadata)})")
            
            # If already a dict, just use it
            if isinstance(self.job_metadata, dict):
                self._processed_metadata = self.job_metadata
                logger.debug("Used metadata directly as dictionary")
            # If string, try to parse as JSON
            elif isinstance(self.job_metadata, str):
                try:
                    # Skip processing if it's a simple string like "dispatch_via_api"
                    if not self.job_metadata.startswith("{") and not self.job_metadata.startswith("["):
                        logger.info(f"Metadata appears to be a simple string, not JSON: {self.job_metadata}")
                        self._processed_metadata = {"raw_value": self.job_metadata}
                        return self._processed_metadata
                        
                    # First parse attempt
                    parsed_data = json.loads(self.job_metadata)
                    logger.debug(f"Initial parsing successful: {type(parsed_data)}")
                    
                    # Check if we got a string (might be double-encoded)
                    if isinstance(parsed_data, str):
                        try:
                            # Second parse attempt for double-encoded JSON
                            logger.info("Detected potential double-encoded JSON, attempting second parse")
                            parsed_data = json.loads(parsed_data)
                            logger.debug("Second parsing successful")
                        except json.JSONDecodeError:
                            # If second parse fails, use the result from first parse
                            logger.debug("Second parsing failed, using result from first parse")
                            pass
                    
                    self._processed_metadata = parsed_data
                    logger.info(f"Successfully parsed metadata: {self._processed_metadata}")
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse job metadata as JSON: {self.job_metadata}. Error: {e}")
                    # Try to salvage something - store as raw_value
                    self._processed_metadata = {"raw_value": self.job_metadata}
            else:
                logger.warning(f"Unknown metadata format: {type(self.job_metadata)}")
                # Convert non-string, non-dict objects to a string representation
                self._processed_metadata = {"raw_value": str(self.job_metadata)}
        except Exception as e:
            logger.error(f"Error processing metadata: {e}")
            self._processed_metadata = {"error": str(e)}
            
        return self._processed_metadata
    
    def get_metadata_field(self, field_name: str, default_value: Any = None) -> Any:
        """
        Helper to safely get a field from the metadata.
        
        Args:
            field_name: The metadata field name to retrieve
            default_value: Value to return if field doesn't exist or metadata isn't available
            
        Returns:
            The field value if found, otherwise the default_value
        """
        metadata = self.processed_metadata
        if not metadata or not isinstance(metadata, dict):
            return default_value
            
        return metadata.get(field_name, default_value)
    
    def get_company_id(self) -> Optional[str]:
        """Helper specifically for getting companyId from metadata."""
        # Try different possible field names
        possible_fields = ["companyId", "company_id", "CompanyId", "companyID", "company"]
        
        for field in possible_fields:
            company_id = self.get_metadata_field(field)
            if company_id:
                logger.info(f"Retrieved companyId from metadata field '{field}': {company_id}")
                return company_id
                
        logger.warning("Company ID not found in any expected metadata fields")
        return None
        
    def get_user_name(self) -> str:
        """Helper specifically for getting user name from metadata."""
        # Try different possible field names
        possible_fields = ["sessionDOName", "sessionName", "name", "user", "userName", "user_name"]
        
        for field in possible_fields:
            user_name = self.get_metadata_field(field)
            if user_name:
                logger.info(f"Retrieved user name from metadata field '{field}': {user_name}")
                return user_name
                
        # If we get here, no name was found
        logger.warning("User name not found in any expected metadata fields")
        
        # Log the entire metadata content for debugging
        metadata = self.processed_metadata
        if metadata:
            logger.info(f"Available metadata fields: {list(metadata.keys())}")
            
        return "there"  # Default fallback

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