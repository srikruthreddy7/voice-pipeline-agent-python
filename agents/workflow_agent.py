import logging
import os
import httpx
import json
from typing import List, Dict, Any, Optional, Annotated
from pydantic import Field

from livekit.plugins import openai
from livekit.agents.llm import function_tool
from livekit.agents.voice import RunContext

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
                "Remember you're speaking to an HVAC technician who understands industry terminology. "
                "Do not mention anything about agents, tools, or assistants in your responses. Never refer to transferring or "
                "handing over to another agent or assistant. Speak naturally as if you're the same person throughout the conversation."
            )
        )
        self.current_workflow = None
        self.current_step_index = 0
        self.workflows_cache = {}  # Cache for workflow ID to name mapping

    async def on_enter(self) -> None:
        """Called when the agent becomes active."""
        await super().on_enter()
        logger.info("WorkflowAgent entered.")
        # REMOVED: context = RunContext(session=self.session) - Cannot create RunContext here
        # REMOVED: try/except block calling list_workflows

        # You might want an initial message here, but it's often better
        # to let the LLM generate the first response based on the transition message
        # from the previous agent (handled in BaseAgent._transfer_to_agent)
        # or based on the initial user prompt if this is the first agent.
        # Example: await self.session.say("I can help you with HVAC workflows. What procedure are you looking for?")

    @function_tool()
    async def list_workflows(self, context: RunContext_T) -> str:
        """Fetches all available workflows from the server."""
        logger.info("Fetching list of workflows from server")
        
        # Get companyId using the simplified helper method
        companyId = context.userdata.get_company_id()
        
        if not companyId:
            logger.warning("Proceeding with workflow list request without companyId")
        
        server_url = os.getenv("AITAS_SERVER_URL")
        if not server_url:
            logger.error("AITAS_SERVER_URL environment variable not set.")
            return "Sorry, I can't access the workflow database due to a configuration issue."
        
        endpoint = f"{server_url.rstrip('/')}/v2/workflows/list"
        
        try:
            async with httpx.AsyncClient() as client:
                # Create request data - for GET request, add params if companyId exists
                params = {}
                if companyId:
                    params["companyId"] = companyId
                
                logger.info(f"Requesting workflows from: {endpoint} with params: {params}")
                
                response = await client.get(
                    endpoint,
                    params=params,
                    timeout=10.0
                )
                response.raise_for_status()
                
                workflows_data = response.json()
                logger.info(f"Retrieved {len(workflows_data)} workflows")
                
                # Update the cache
                self.workflows_cache = {w['id']: w.get('name', f"Workflow {w['id']}") 
                                       for w in workflows_data if 'id' in w}
                
                # Format a nice response for the user
                if not workflows_data:
                    return "I don't have any workflows available right now. Would you like me to create a custom workflow for you instead?"
                
                workflow_list = []
                for w in workflows_data:
                    name = w.get('name', f"Workflow {w.get('id', 'Unknown')}")
                    description = w.get('description', '')
                    if description:
                        workflow_list.append(f"• {name} - {description}")
                    else:
                        workflow_list.append(f"• {name}")
                
                workflow_text = "\n".join(workflow_list)
                
                return f"Here are the available workflows I can help you with:\n\n{workflow_text}\n\nWhich one would you like to use?"
        except Exception as e:
            logger.error(f"Error fetching workflows: {e}")
            return "Sorry, I couldn't retrieve the list of workflows. Would you like me to try again or assist you with something else?"

    @function_tool()
    async def get_workflow(self, workflow_id: Annotated[str, Field(description="The ID of the workflow to retrieve")], context: RunContext_T) -> str:
        """Fetches a specific workflow by ID from the server, sending company context."""
        logger.info(f"Fetching workflow with ID: {workflow_id}")
        
        # Get companyId using the simplified helper method  
        companyId = context.userdata.get_company_id()
        
        if not companyId:
            logger.warning("Proceeding with workflow request without companyId")

        server_url = os.getenv("AITAS_SERVER_URL")
        if not server_url:
            logger.error("AITAS_SERVER_URL environment variable not set.")
            return "Sorry, I can't access the workflow database due to a configuration issue."
        
        # Use the correct endpoint with query parameters instead of path
        endpoint = f"{server_url.rstrip('/')}/v2/workflows/get"
        
        try:
            async with httpx.AsyncClient() as client:
                # Create query parameters for both workflow_id and companyId
                params = {}
                if companyId:
                    params["companyId"] = companyId
                if workflow_id:
                    params["id"] = workflow_id
                
                logger.info(f"Requesting workflow from: {endpoint} with params: {params}")
                
                # Use GET and send parameters as query params
                response = await client.get(
                    endpoint,
                    params=params,
                    timeout=10.0
                )
                response.raise_for_status()
                
                # The response is now an array of steps directly
                steps_data = response.json()
                logger.info(f"Retrieved workflow steps: {len(steps_data)} steps")
                
                # Verify the response is a list
                if not isinstance(steps_data, list):
                    logger.error(f"Unexpected response format. Expected array but got: {type(steps_data)}")
                    return "Sorry, I received an unexpected response format from the workflow database. Please try again later."
                
                # Look up the workflow name from cache if available
                workflow_name = self.workflows_cache.get(workflow_id, f"Workflow {workflow_id}")
                
                # Create a workflow model with the available information
                workflow_data = {
                    "id": workflow_id,
                    "name": workflow_name,
                    "description": f"Workflow ID: {workflow_id}",
                    "steps": steps_data
                }
                
                # Create a workflow model and store it
                self.current_workflow = WorkflowModel.from_json(workflow_data)
                self.current_step_index = 0
                
                # Format the response
                workflow_name = self.current_workflow.name
                total_steps = len(self.current_workflow.steps)
                
                if total_steps == 0:
                    return f"I found the '{workflow_name}' workflow, but it doesn't have any steps defined yet. Would you like to try a different workflow?"
                
                first_step = self.current_workflow.steps[0] if self.current_workflow.steps else {}
                first_step_description = first_step.get('description', 'No step description available')
                
                return (
                    f"I've loaded the '{workflow_name}' workflow.\n\n"
                    f"This workflow has {total_steps} steps. Let's start with the first step:\n\n"
                    f"Step 1: {first_step_description}\n\n"
                    f"Let me know when you've completed this step or if you need any clarification."
                )
                
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.error(f"Workflow ID {workflow_id} not found (or not accessible for company {companyId})")
                return f"I couldn't find a workflow with the ID '{workflow_id}' for your context. Would you like to see a list of available workflows instead?"
            else:
                logger.error(f"HTTP error fetching workflow {workflow_id}: {e}")
                return f"Sorry, I encountered an error retrieving the workflow (Error: {e.response.status_code}). Would you like to try again or choose a different workflow?"
        except Exception as e:
            logger.error(f"Unexpected error fetching workflow {workflow_id}: {e}")
            return f"Sorry, something went wrong while retrieving the workflow. Would you like to try again or see a list of available workflows?"

    @function_tool()
    async def find_workflow_by_name(self, workflow_name: Annotated[str, Field(description="The name of the workflow to search for")], context: RunContext_T) -> str:
        """Searches for workflows that match a given name and returns options."""
        logger.info(f"Searching for workflow with name: {workflow_name}")
        
        # First, make sure we have workflows in the cache
        if not self.workflows_cache:
            logger.info("Workflow cache empty, fetching workflows first")
            await self.list_workflows(context)
            
            # If still empty after fetching, there are no workflows
            if not self.workflows_cache:
                return "I couldn't find any workflows in the system. Would you like me to assist you with something else?"
        
        # Search for workflows that contain the provided name (case-insensitive)
        workflow_name_lower = workflow_name.lower()
        matching_workflows = [
            (workflow_id, name) 
            for workflow_id, name in self.workflows_cache.items() 
            if workflow_name_lower in name.lower()
        ]
        
        # If there's only one match, get it directly
        if len(matching_workflows) == 1:
            workflow_id, name = matching_workflows[0]
            logger.info(f"Found exact match for workflow: {name} (ID: {workflow_id})")
            
            # Get the complete workflow using the ID
            return await self.get_workflow(workflow_id, context)
            
        # If there are multiple matches, show options
        elif len(matching_workflows) > 1:
            workflow_list = "\n".join([f"• {name} (ID: {workflow_id})" for workflow_id, name in matching_workflows])
            return (
                f"I found {len(matching_workflows)} workflows matching '{workflow_name}':\n\n"
                f"{workflow_list}\n\n"
                f"Which one would you like to use? Please specify the name or ID."
            )
            
        # No matches found
        else:
            return (
                f"I couldn't find any workflows matching '{workflow_name}'. "
                f"Would you like to see a list of all available workflows instead?"
            )

    @function_tool()
    async def next_step(self, context: RunContext_T) -> str:
        """Moves to the next step in the current workflow."""
        if not self.current_workflow:
            return "There is no active workflow. Would you like me to help you find one?"
        
        total_steps = len(self.current_workflow.steps)
        if total_steps == 0:
            return "The current workflow doesn't have any steps defined."
        
        # Check if we're already at the last step
        if self.current_step_index >= total_steps - 1:
            return f"You've completed all {total_steps} steps in this workflow! Is there anything else you'd like help with?"
        
        # Move to the next step
        self.current_step_index += 1
        current_step = self.current_workflow.steps[self.current_step_index]
        
        # Format the response
        step_num = self.current_step_index + 1  # 1-indexed for user display
        step_description = current_step.get('description', 'No description available')
        
        return (
            f"Step {step_num} of {total_steps}:\n\n"
            f"{step_description}\n\n"
            f"Let me know when you've completed this step or if you need any clarification."
        )
    
    @function_tool()
    async def previous_step(self, context: RunContext_T) -> str:
        """Moves to the previous step in the current workflow."""
        if not self.current_workflow:
            return "There is no active workflow. Would you like me to help you find one?"
        
        total_steps = len(self.current_workflow.steps)
        if total_steps == 0:
            return "The current workflow doesn't have any steps defined."
        
        # Check if we're at the first step
        if self.current_step_index <= 0:
            return "You're already at the first step of this workflow. Would you like me to repeat the instructions?"
        
        # Move to the previous step
        self.current_step_index -= 1
        current_step = self.current_workflow.steps[self.current_step_index]
        
        # Format the response
        step_num = self.current_step_index + 1  # 1-indexed for user display
        step_description = current_step.get('description', 'No description available')
        
        return (
            f"Going back to Step {step_num} of {total_steps}:\n\n"
            f"{step_description}\n\n"
            f"Let me know when you're ready to continue."
        )
    
    @function_tool()
    async def jump_to_step(self, step_number: Annotated[int, Field(description="The step number to jump to (1-indexed)")], context: RunContext_T) -> str:
        """Jumps to a specific step in the current workflow."""
        if not self.current_workflow:
            return "There is no active workflow. Would you like me to help you find one?"
        
        total_steps = len(self.current_workflow.steps)
        if total_steps == 0:
            return "The current workflow doesn't have any steps defined."
        
        # Convert to 0-indexed for internal use
        target_index = step_number - 1
        
        # Validate the step number
        if target_index < 0 or target_index >= total_steps:
            return f"Invalid step number. This workflow has {total_steps} steps (1-{total_steps})."
        
        # Jump to the specified step
        self.current_step_index = target_index
        current_step = self.current_workflow.steps[self.current_step_index]
        
        # Format the response
        step_description = current_step.get('description', 'No description available')
        
        return (
            f"Step {step_number} of {total_steps}:\n\n"
            f"{step_description}\n\n"
            f"Let me know when you've completed this step or if you need help."
        )
    
    @function_tool()
    async def current_step(self, context: RunContext_T) -> str:
        """Shows the current step in the workflow again."""
        if not self.current_workflow:
            return "There is no active workflow. Would you like me to help you find one?"
        
        total_steps = len(self.current_workflow.steps)
        if total_steps == 0:
            return "The current workflow doesn't have any steps defined."
        
        # Get the current step
        current_step = self.current_workflow.steps[self.current_step_index]
        
        # Format the response
        step_num = self.current_step_index + 1  # 1-indexed for user display
        step_description = current_step.get('description', 'No description available')
        
        return (
            f"Current Step ({step_num} of {total_steps}):\n\n"
            f"{step_description}\n\n"
            f"Let me know when you've completed this step or if you need any clarification."
        ) 