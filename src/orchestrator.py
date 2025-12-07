"""
orchestrator.py

Agentic AI Orchestrator for Structural Engineering FEA Simulations.

This module uses LangGraph for state management and Google Gemini for 
natural language to structured JSON conversion. It orchestrates the 
workflow from user input to FEA job submission.

Architecture:
- LangGraph StateGraph: Manages the agent workflow
- Google Gemini 1.5 Pro: LLM for parsing natural language
- Pydantic Models: Validation of structured outputs
- MCP Server: Backend API for job submission
"""

import os
import requests
from typing import TypedDict, Annotated, Optional, Sequence
from dotenv import load_dotenv

# LangChain and LangGraph imports
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages

# Local imports
from mcp_schema import AbaqusInput, Geometry, Material, Loading, Discretization

# Load environment variables
load_dotenv()

# Configuration
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8000")

if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEY not found in environment variables. Please set it in .env file.")


# ============================================================================
# STATE DEFINITION
# ============================================================================

class AgentState(TypedDict):
    """
    The state object that flows through the LangGraph workflow.
    
    Attributes:
        messages: Conversation history (LangChain messages)
        raw_input: Original user request (natural language)
        structured_config: Parsed AbaqusInput object (if successful)
        validation_error: Error message from physics validation (if any)
        submission_status: Result from MCP Server job submission
    """
    messages: Annotated[Sequence[BaseMessage], add_messages]
    raw_input: str
    structured_config: Optional[AbaqusInput]
    validation_error: Optional[str]
    submission_status: Optional[str]


# ============================================================================
# LLM INITIALIZATION
# ============================================================================

# Initialize Google Gemini with structured output capability
llm = ChatGoogleGenerativeAI(
    model="gemini-3.0-flash",
    google_api_key=GOOGLE_API_KEY,
    temperature=0.0,  # Deterministic for parsing
    convert_system_message_to_human=True
)

# Bind the LLM to output structured AbaqusInput objects
structured_llm = llm.with_structured_output(AbaqusInput)


# ============================================================================
# GRAPH NODE FUNCTIONS
# ============================================================================

def parse_request(state: AgentState) -> AgentState:
    """
    Node 1: Parse Request
    
    Uses Google Gemini to convert natural language input into a structured
    AbaqusInput configuration. The LLM is guided by the Pydantic schema.
    
    Transition: Always proceeds to validate_physics
    """
    print("🔍 [Node: parse_request] Extracting structured data from user input...")
    
    # Construct a prompt that guides the LLM to extract FEA parameters
    system_prompt = """You are an expert structural engineering assistant specializing in Finite Element Analysis (FEA).
Your task is to extract simulation parameters from natural language descriptions and format them into a structured JSON configuration.

Extract the following information:
1. MODEL_NAME: A descriptive name for the simulation
2. TEST_TYPE: One of [CantileverBeam, TaylorImpact, TensionTest]
3. GEOMETRY: Length, width, height in meters
4. MATERIAL: Name, Young's modulus (Pa), Poisson's ratio
5. LOADING: Applied forces in Newtons
6. DISCRETIZATION: Number of mesh elements along each axis

Use reasonable engineering defaults if specific values are not provided:
- Steel: E=200 GPa (200e9 Pa), ν=0.3
- Aluminum: E=69 GPa (69e9 Pa), ν=0.33
- Default mesh: 10 elements per dimension

Be precise with units and ensure all values are physically meaningful."""
    
    user_input = state["raw_input"]
    
    # Create message list for the LLM
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"Convert this simulation request into structured parameters: {user_input}")
    ]
    
    try:
        # Invoke the structured LLM - it will return an AbaqusInput object
        structured_config = structured_llm.invoke(messages)
        
        print(f"✅ Successfully parsed configuration:")
        print(f"   Model: {structured_config.MODEL_NAME}")
        print(f"   Test Type: {structured_config.TEST_TYPE}")
        print(f"   Material: {structured_config.MATERIAL.name}")
        
        # Update state with parsed configuration
        state["structured_config"] = structured_config
        state["messages"].append(AIMessage(content=f"Successfully parsed simulation parameters for {structured_config.MODEL_NAME}"))
        
    except Exception as e:
        error_msg = f"Failed to parse input: {str(e)}"
        print(f"❌ {error_msg}")
        state["validation_error"] = error_msg
        state["messages"].append(AIMessage(content=error_msg))
    
    return state


def validate_physics(state: AgentState) -> AgentState:
    """
    Node 2: Validate Physics
    
    Performs engineering sanity checks on the structured configuration.
    Validates material properties, geometry constraints, and loading conditions.
    
    Transition: 
        - If valid -> proceed to submit_job
        - If invalid -> END (terminates workflow with error)
    """
    print("🔬 [Node: validate_physics] Performing engineering validation...")
    
    structured_config = state.get("structured_config")
    
    # If parsing failed, skip validation
    if not structured_config:
        state["validation_error"] = "No structured configuration to validate (parsing failed)"
        return state
    
    validation_errors = []
    
    # ---- Material Physics Checks ----
    material = structured_config.MATERIAL
    
    # Check 1: Poisson's ratio must be between 0.0 and 0.5 for stable materials
    if material.poisson_ratio < 0.0 or material.poisson_ratio > 0.5:
        validation_errors.append(
            f"Invalid Poisson's ratio ({material.poisson_ratio}). "
            f"Must be between 0.0 and 0.5 for physically stable materials."
        )
    
    # Check 2: Young's modulus should be positive and within reasonable engineering range
    if material.youngs_modulus_pa <= 0:
        validation_errors.append(f"Young's modulus must be positive (got {material.youngs_modulus_pa} Pa)")
    elif material.youngs_modulus_pa < 1e6:  # Less than 1 MPa is suspiciously low
        validation_errors.append(
            f"Young's modulus ({material.youngs_modulus_pa} Pa) seems too low. "
            f"Typical engineering materials range from 1 GPa to 1000 GPa."
        )
    elif material.youngs_modulus_pa > 1e12:  # Greater than 1000 GPa is suspiciously high
        validation_errors.append(
            f"Young's modulus ({material.youngs_modulus_pa} Pa) seems too high. "
            f"Check if units are correct (should be in Pascals)."
        )
    
    # ---- Geometry Checks ----
    geometry = structured_config.GEOMETRY
    
    # Check 3: All dimensions must be positive (already enforced by Pydantic, but double-check)
    if geometry.length_m <= 0 or geometry.width_m <= 0 or geometry.height_m <= 0:
        validation_errors.append("All geometry dimensions must be positive")
    
    # Check 4: Warn about extreme aspect ratios (could cause mesh issues)
    aspect_ratios = [
        geometry.length_m / geometry.width_m,
        geometry.length_m / geometry.height_m,
        geometry.width_m / geometry.height_m
    ]
    max_aspect_ratio = max(aspect_ratios)
    if max_aspect_ratio > 100:
        validation_errors.append(
            f"Extreme aspect ratio detected ({max_aspect_ratio:.1f}). "
            f"This may cause meshing or convergence issues."
        )
    
    # ---- Loading Checks ----
    loading = structured_config.LOADING
    
    # Check 5: For CantileverBeam, tip load should be reasonable
    if structured_config.TEST_TYPE == "CantileverBeam":
        if abs(loading.tip_load_n) < 0.001:
            validation_errors.append("Tip load is too small - results may be meaningless")
        elif abs(loading.tip_load_n) > 1e9:
            validation_errors.append("Tip load seems extremely large - check units (should be in Newtons)")
    
    # ---- Discretization Checks ----
    discretization = structured_config.DISCRETIZATION
    
    # Check 6: Mesh density should be reasonable
    total_elements = (discretization.elements_length * 
                     discretization.elements_width * 
                     discretization.elements_height)
    
    if total_elements < 8:
        validation_errors.append(
            f"Mesh is too coarse ({total_elements} elements). "
            f"Use at least 2 elements per dimension for meaningful results."
        )
    elif total_elements > 1_000_000:
        validation_errors.append(
            f"Mesh is very fine ({total_elements} elements). "
            f"This will require significant computational resources."
        )
    
    # ---- Compile Results ----
    if validation_errors:
        error_message = "Physics validation failed:\n" + "\n".join(f"  - {err}" for err in validation_errors)
        print(f"❌ {error_message}")
        state["validation_error"] = error_message
        state["messages"].append(AIMessage(content=error_message))
    else:
        success_msg = f"✅ Physics validation passed for {structured_config.MODEL_NAME}"
        print(success_msg)
        state["validation_error"] = None
        state["messages"].append(AIMessage(content="Physics validation passed successfully"))
    
    return state


def submit_job(state: AgentState) -> AgentState:
    """
    Node 3: Submit Job
    
    Sends the validated AbaqusInput configuration to the MCP Server via POST request.
    The server will initialize a new FEA job and return a job context.
    
    Transition: Always proceeds to END (workflow complete)
    """
    print("🚀 [Node: submit_job] Submitting job to MCP Server...")
    
    structured_config = state["structured_config"]
    
    # Prepare the API request payload
    endpoint = f"{MCP_SERVER_URL}/mcp/init"
    payload = {
        "job_name": structured_config.MODEL_NAME,
        "initial_input": structured_config.model_dump()
    }
    
    try:
        # Make POST request to MCP Server
        response = requests.post(endpoint, json=payload, timeout=10)
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


# ============================================================================
# CONDITIONAL ROUTING LOGIC
# ============================================================================

def should_continue_to_submit(state: AgentState) -> str:
    """
    Conditional edge function that decides the next step after validation.
    
    Returns:
        - "submit_job" if validation passed
        - "END" if validation failed
    """
    if state.get("validation_error"):
        print("⚠️  [Router] Validation failed - terminating workflow")
        return "END"
    else:
        print("✅ [Router] Validation passed - proceeding to job submission")
        return "submit_job"


# ============================================================================
# LANGGRAPH WORKFLOW CONSTRUCTION
# ============================================================================

def create_orchestrator_graph() -> StateGraph:
    """
    Constructs the LangGraph StateGraph for the orchestrator workflow.
    
    Workflow:
        START -> parse_request -> validate_physics -> (conditional)
                                                    -> submit_job -> END
                                                    -> END (if validation fails)
    
    Returns:
        Compiled StateGraph ready for execution
    """
    # Initialize the graph with our state schema
    workflow = StateGraph(AgentState)
    
    # Add nodes (processing functions)
    workflow.add_node("parse_request", parse_request)
    workflow.add_node("validate_physics", validate_physics)
    workflow.add_node("submit_job", submit_job)
    
    # Define edges (transitions between nodes)
    
    # 1. Entry point: Start -> parse_request
    workflow.set_entry_point("parse_request")
    
    # 2. Always go from parse_request -> validate_physics
    workflow.add_edge("parse_request", "validate_physics")
    
    # 3. Conditional routing from validate_physics
    workflow.add_conditional_edges(
        "validate_physics",
        should_continue_to_submit,
        {
            "submit_job": "submit_job",  # If validation passes
            "END": END  # If validation fails
        }
    )
    
    # 4. Always end after job submission
    workflow.add_edge("submit_job", END)
    
    # Compile the graph into an executable workflow
    return workflow.compile()


# ============================================================================
# MAIN ORCHESTRATOR INTERFACE
# ============================================================================

def run_orchestrator(user_input: str) -> AgentState:
    """
    Main entry point for the orchestrator.
    
    Takes natural language input, processes it through the LangGraph workflow,
    and returns the final state containing all results.
    
    Args:
        user_input: Natural language description of the FEA simulation
        
    Returns:
        Final AgentState with structured config, validation results, and submission status
        
    Example:
        >>> result = run_orchestrator(
        ...     "Run a cantilever beam test with steel, 1 meter long, 0.1m x 0.1m cross-section, "
        ...     "apply 1000N downward force at the tip"
        ... )
        >>> print(result["submission_status"])
    """
    print("=" * 80)
    print("🤖 AGENTIC FEA ORCHESTRATOR")
    print("=" * 80)
    print(f"📝 User Input: {user_input}\n")
    
    # Initialize the state
    initial_state: AgentState = {
        "messages": [HumanMessage(content=user_input)],
        "raw_input": user_input,
        "structured_config": None,
        "validation_error": None,
        "submission_status": None
    }
    
    # Create and execute the workflow graph
    app = create_orchestrator_graph()
    final_state = app.invoke(initial_state)
    
    print("\n" + "=" * 80)
    print("🏁 WORKFLOW COMPLETE")
    print("=" * 80)
    
    # Print summary
    if final_state.get("submission_status"):
        print(f"Status: {final_state['submission_status']}")
    if final_state.get("validation_error"):
        print(f"Validation Error: {final_state['validation_error']}")
    
    return final_state


# ============================================================================
# COMMAND-LINE INTERFACE (for testing)
# ============================================================================

if __name__ == "__main__":
    """
    Test the orchestrator with example inputs.
    """
    
    # Example 1: Simple cantilever beam
    example_input = (
        "Create a cantilever beam simulation called 'Steel_Beam_Test_001'. "
        "Use a steel beam that is 2 meters long, 0.1 meters wide, and 0.05 meters tall. "
        "Apply a downward force of 5000 Newtons at the free end. "
        "Use 20 elements along the length, 5 along the width, and 3 along the height."
    )
    
    print("\n🧪 Running test simulation...\n")
    result = run_orchestrator(example_input)
    
    # Access the results
    if result.get("structured_config"):
        print("\n📊 Parsed Configuration:")
        config = result["structured_config"]
        print(f"   Model: {config.MODEL_NAME}")
        print(f"   Test: {config.TEST_TYPE}")
        print(f"   Material: {config.MATERIAL.name} (E={config.MATERIAL.youngs_modulus_pa/1e9:.1f} GPa)")
        print(f"   Geometry: {config.GEOMETRY.length_m}m × {config.GEOMETRY.width_m}m × {config.GEOMETRY.height_m}m")
        print(f"   Load: {config.LOADING.tip_load_n}N")
    
    print("\n✨ Orchestrator test complete!")
