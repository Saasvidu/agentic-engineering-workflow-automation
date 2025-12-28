# nodes.py
"""
Agent node functions for the orchestrator workflow.
Each function represents a step in the FEA job submission pipeline.
"""

import requests
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
import sys
from pathlib import Path

# Add parent directories to path to import shared schema
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from shared.mcp_schema import AbaqusInput

# Handle imports - try absolute first, fall back to relative
try:
    from orchestrator.config import MCP_SERVER_URL, llm
    from orchestrator.prompts import PARSE_REQUEST_PROMPT
    from orchestrator.state import AgentState
except ImportError:
    from .config import MCP_SERVER_URL, llm
    from .prompts import PARSE_REQUEST_PROMPT
    from .state import AgentState

# Create structured LLM for parsing
structured_llm = llm.with_structured_output(AbaqusInput)


def parse_request(state: AgentState) -> AgentState:
    """
    Node 1: Parse Request
    Uses OpenAI to convert natural language input into a structured
    AbaqusInput configuration.
    """
    print("🔍 [Node: parse_request] Extracting structured data from user input...")
    
    user_input = state["raw_input"]
    
    messages = [
        SystemMessage(content=PARSE_REQUEST_PROMPT),
        HumanMessage(content=f"Convert this simulation request into structured parameters: {user_input}")
    ]
    
    try:
        # Invoke the structured LLM
        structured_config = structured_llm.invoke(messages)
        
        print(f"✅ Successfully parsed configuration:")
        print(f"   Model: {structured_config.MODEL_NAME}")
        print(f"   Test Type: {structured_config.TEST_TYPE}")
        print(f"   Material: {structured_config.MATERIAL.name}")
        
        state["structured_config"] = structured_config
        state["messages"].append(
            AIMessage(content=f"Successfully parsed parameters for {structured_config.MODEL_NAME}")
        )
        
    except Exception as e:
        error_msg = f"Failed to parse input: {str(e)}"
        print(f"❌ {error_msg}")
        state["validation_error"] = error_msg
        state["messages"].append(AIMessage(content=error_msg))
    
    return state


def validate_physics(state: AgentState) -> AgentState:
    """
    Node 2: Validate Physics
    Performs engineering validation on the parsed AbaqusInput configuration.
    Ensures the parameters are physically realistic and compliant with FEA best practices.
    Returns the state with validation errors if any.
    """
    print("🔬 [Node: validate_physics] Performing engineering validation...")
    structured_config = state.get("structured_config")
    
    if not structured_config:
        state["validation_error"] = "No structured configuration to validate"
        return state

    # Check aspect ratio
    if structured_config.GEOMETRY.length_m / structured_config.GEOMETRY.width_m < 10:
        state["validation_error"] = "Aspect ratio is too large. Should be at least 10:1."
        return state

    # Check material properties
    if structured_config.MATERIAL.youngs_modulus_pa < 1e9:
        state["validation_error"] = "Young's modulus is too low. Should be at least 1 GPa."
        return state

    # Check discretization
    if structured_config.DISCRETIZATION.elements_length < 10:
        state["validation_error"] = "Discretization is too coarse. Should be at least 10 elements."
        return state

    # Check loading
    if structured_config.LOADING.tip_load_n < 1000:
        state["validation_error"] = "Loading is too low. Should be at least 1000 N."
        return state

    # Check if all checks passed
    state["validation_error"] = None
    return state


def submit_job(state: AgentState) -> AgentState:
    """
    Node 3: Submit Job
    Sends the validated AbaqusInput configuration to the MCP Server via POST request.
    The server will initialize a new FEA job and return a job context.
    Returns the state with submission errors if any.
    """
    print("🚀 [Node: submit_job] Submitting job to MCP Server...")
    
    structured_config = state["structured_config"]
    
    if not structured_config:
        error_msg = "No structured configuration to submit"
        state["submission_status"] = f"FAILED: {error_msg}"
        state["messages"].append(AIMessage(content=error_msg))
        return state
    
    # Prepare the API request
    endpoint = f"{MCP_SERVER_URL}/mcp/init"
    params = {"job_name": structured_config.MODEL_NAME}
    payload = structured_config.model_dump()
    
    # Debug: Show the endpoint being used
    print(f"   📡 Endpoint: {endpoint}")
    print(f"   📡 MCP_SERVER_URL value: {repr(MCP_SERVER_URL)}")
    
    try:
        # Make POST request to MCP Server with job_name as query param and config as JSON body
        response = requests.post(endpoint, params=params, json=payload, timeout=10)
        response.raise_for_status()
        
        # Parse response
        job_context = response.json()
        job_id = job_context.get("job_id", "Unknown")
        
        success_msg = (
            f"✅ Job submitted successfully!\n"
            f"   Job ID: {job_id}\n"
            f"   Job Name: {structured_config.MODEL_NAME}\n"
            f"   Status: {job_context.get('current_status', 'INITIALIZED')}"
        )
        print(success_msg)
        
        state["submission_status"] = f"SUCCESS: Job ID {job_id}"
        state["messages"].append(AIMessage(content=success_msg))
        
    except requests.exceptions.RequestException as e:
        error_msg = f"Failed to submit job to MCP Server: {str(e)}"
        print(f"❌ {error_msg}")
        state["submission_status"] = f"FAILED: {str(e)}"
        state["messages"].append(AIMessage(content=error_msg))
    
    return state


def should_continue_to_submit(state: AgentState) -> str:
    """
    Conditional edge function: determines whether to proceed to submission
    or end the workflow based on validation errors.
    """
    if state.get("validation_error"):
        return "END"
    return "submit_job"

