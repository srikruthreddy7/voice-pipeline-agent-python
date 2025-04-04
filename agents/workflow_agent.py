import logging
import os
import httpx
from typing import List, Dict, Any, Optional, Annotated
from pydantic import Field

from livekit.plugins import openai
from livekit.agents.llm import function_tool

from .base import BaseAgent, RunContext_T

# Placeholder for voice ID
# voice_id = "your_workflow_voice_id"

logger = logging.getLogger(__name__)

class WorkflowModel:
    """Simple model to represent a workflow."""
    def __init__(self, workflow_id: str, name: str, description: str, steps: List[Dict[str, Any]]):
        self.id = workflow_id
        self.name = name
        self.description = description
        self.steps = steps
        
    @staticmethod
    def from_json(workflow_json: Dict[str, Any]) -> 'WorkflowModel':
        """Create a WorkflowModel from JSON data."""
        return WorkflowModel(
            workflow_id=workflow_json.get('id', ''),
            name=workflow_json.get('name', 'Unnamed Workflow'),
            description=workflow_json.get('description', 'No description available'),
            steps=workflow_json.get('steps', [])
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'steps': self.steps
        }
    
    def __str__(self):
        """String representation for logging."""
        return f"Workflow '{self.name}' (ID: {self.id}) with {len(self.steps)} steps"

class WorkflowAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            instructions=(
                "You are the Workflow Agent, an HVAC specialist who guides technicians through standardized procedures. "
                "You maintain a helpful, professional tone while leading users through step-by-step workflows. "
                "When a user asks for a workflow, first check if they specified a name or topic. "
                "If they did, use find_workflow_by_name to locate the matching workflow. "
                "If they didn't specify one, use list_workflows to show available options and ask them to choose. "
                "Once a workflow is selected, use get_workflow to retrieve the full details and guide the user through each step. "
                "For each step, clearly explain what needs to be done and wait for confirmation before proceeding to the next step. "
                "If the user has questions about a specific step, answer professionally with technical accuracy. "
                "If they need to go back to a previous step or skip ahead, accommodate their request. "
                "Remember you're speaking to an HVAC technician who understands industry terminology."
            )
        )
        self.current_workflow = None
        self.current_step_index = 0
        self.workflows_cache = {}  # Cache for workflow ID to name mapping

    async def on_enter(self) -> None:
        await super().on_enter()
        logger.info("WorkflowAgent entered. Fetching available workflows...")
        try:
            # Automatically fetch and cache available workflows on enter
            await self.list_workflows()
            # Initial message will be provided by the function tool
        except Exception as e:
            logger.error(f"Error fetching workflows: {e}")
            initial_message = "I'm here to guide you through HVAC workflows, but I'm having trouble accessing the workflow database. What would you like help with today?"
            return initial_message

    @function_tool()
    async def list_workflows(self) -> str:
        """Fetches all available workflows from the server."""
        logger.info("Fetching list of workflows from server")
        server_url = os.getenv("AITAS_SERVER_URL")
        if not server_url:
            logger.error("AITAS_SERVER_URL environment variable not set.")
            return "Sorry, I can't access the workflow database due to a configuration issue."
        
        endpoint = f"{server_url.rstrip('/')}/v2/workflows"
        logger.info(f"Requesting workflows from: {endpoint}")
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    endpoint,
                    timeout=10.0
                )
                response.raise_for_status()
                
                workflows_data = response.json()
                logger.info(f"Retrieved {len(workflows_data)} workflows")
                
                # Update the cache
                self.workflows_cache = {w['id']: w['name'] for w in workflows_data if 'id' in w and 'name' in w}
                
                # Format a nice response for the user
                if not workflows_data:
                    return "I don't have any workflows available right now. Would you like me to create a custom workflow for you instead?"
                
                workflow_list = "\n".join([f"• {w.get('name', 'Unnamed')} - {w.get('description', 'No description')}" 
                                         for w in workflows_data])
                
                return f"Here are the available workflows I can help you with:\n\n{workflow_list}\n\nWhich one would you like to use?"
                
        except httpx.RequestError as e:
            logger.error(f"HTTP error occurred while fetching workflows: {e}")
            return "Sorry, I'm having trouble connecting to the workflow database right now. Can I assist you with something else instead?"
        except Exception as e:
            logger.error(f"Unexpected error fetching workflows: {e}")
            return "Sorry, something went wrong while retrieving the workflows. Is there anything specific you'd like help with?"

    @function_tool()
    async def get_workflow(self, workflow_id: Annotated[str, Field(description="The ID of the workflow to retrieve")]) -> str:
        """Fetches a specific workflow by ID from the server."""
        logger.info(f"Fetching workflow with ID: {workflow_id}")
        server_url = os.getenv("AITAS_SERVER_URL")
        if not server_url:
            logger.error("AITAS_SERVER_URL environment variable not set.")
            return "Sorry, I can't access the workflow database due to a configuration issue."
        
        endpoint = f"{server_url.rstrip('/')}/v2/workflows/{workflow_id}"
        logger.info(f"Requesting workflow from: {endpoint}")
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    endpoint,
                    timeout=10.0
                )
                response.raise_for_status()
                
                workflow_data = response.json()
                logger.info(f"Retrieved workflow: {workflow_data.get('name', 'Unnamed')}")
                
                # Create a workflow model and store it
                self.current_workflow = WorkflowModel.from_json(workflow_data)
                self.current_step_index = 0
                
                # Format the response
                workflow_name = self.current_workflow.name
                workflow_description = self.current_workflow.description
                total_steps = len(self.current_workflow.steps)
                
                if total_steps == 0:
                    return f"I found the '{workflow_name}' workflow, but it doesn't have any steps defined yet. Would you like to try a different workflow?"
                
                first_step = self.current_workflow.steps[0] if self.current_workflow.steps else {}
                first_step_description = first_step.get('description', 'No step description available')
                
                return (
                    f"I've loaded the '{workflow_name}' workflow: {workflow_description}\n\n"
                    f"This workflow has {total_steps} steps. Let's start with the first step:\n\n"
                    f"Step 1: {first_step_description}\n\n"
                    f"Let me know when you've completed this step or if you need any clarification."
                )
                
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.error(f"Workflow ID {workflow_id} not found")
                return f"I couldn't find a workflow with the ID '{workflow_id}'. Would you like to see a list of available workflows instead?"
            else:
                logger.error(f"HTTP error fetching workflow {workflow_id}: {e}")
                return f"Sorry, I encountered an error retrieving the workflow (Error: {e.response.status_code}). Would you like to try again or choose a different workflow?"
        except Exception as e:
            logger.error(f"Unexpected error fetching workflow {workflow_id}: {e}")
            return f"Sorry, something went wrong while retrieving the workflow. Would you like to try again or see a list of available workflows?"

    @function_tool()
    async def find_workflow_by_name(self, workflow_name: Annotated[str, Field(description="The name or keywords to search for in workflow names")]) -> str:
        """Finds a workflow ID by matching its name or keywords, then retrieves it."""
        logger.info(f"Searching for workflow matching: '{workflow_name}'")
        
        # If cache is empty, populate it
        if not self.workflows_cache:
            list_result = await self.list_workflows()
            # If there was an error fetching workflows, return the error message
            if "Sorry" in list_result or "I don't have any" in list_result:
                return list_result
        
        # Search for the workflow by name (case-insensitive partial match)
        search_term = workflow_name.lower()
        matches = []
        
        for workflow_id, name in self.workflows_cache.items():
            if search_term in name.lower():
                matches.append((workflow_id, name))
        
        # Handle search results
        if len(matches) == 0:
            return f"I couldn't find any workflows matching '{workflow_name}'. Would you like to see a list of all available workflows?"
        
        elif len(matches) == 1:
            # Exact match found, proceed to load the workflow
            workflow_id, matched_name = matches[0]
            logger.info(f"Found exact match for '{workflow_name}': '{matched_name}' (ID: {workflow_id})")
            return await self.get_workflow(workflow_id)
        
        else:
            # Multiple matches, ask user to clarify
            options = "\n".join([f"• {name}" for workflow_id, name in matches])
            return f"I found multiple workflows that might match '{workflow_name}':\n\n{options}\n\nWhich one would you like to use?"

    @function_tool()
    async def next_step(self) -> str:
        """Moves to the next step in the current workflow."""
        if not self.current_workflow:
            return "There's no active workflow. Would you like to see a list of available workflows?"
        
        if not self.current_workflow.steps:
            return f"The '{self.current_workflow.name}' workflow doesn't have any steps defined."
        
        total_steps = len(self.current_workflow.steps)
        self.current_step_index += 1
        
        if self.current_step_index >= total_steps:
            return f"That completes all {total_steps} steps of the '{self.current_workflow.name}' workflow. Is there anything else you'd like help with?"
        
        current_step = self.current_workflow.steps[self.current_step_index]
        step_description = current_step.get('description', 'No description available')
        
        return f"Step {self.current_step_index + 1} of {total_steps}: {step_description}\n\nLet me know when you're ready to proceed to the next step."

    @function_tool()
    async def previous_step(self) -> str:
        """Goes back to the previous step in the current workflow."""
        if not self.current_workflow:
            return "There's no active workflow. Would you like to see a list of available workflows?"
        
        if not self.current_workflow.steps:
            return f"The '{self.current_workflow.name}' workflow doesn't have any steps defined."
        
        if self.current_step_index <= 0:
            self.current_step_index = 0
            return "You're already at the first step of the workflow."
        
        self.current_step_index -= 1
        current_step = self.current_workflow.steps[self.current_step_index]
        step_description = current_step.get('description', 'No description available')
        
        total_steps = len(self.current_workflow.steps)
        return f"Going back to step {self.current_step_index + 1} of {total_steps}: {step_description}" 