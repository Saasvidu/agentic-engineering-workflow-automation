import os
import requests
import sys
from pathlib import Path
from typing import TypedDict, Annotated, Optional, Sequence
from dotenv import load_dotenv

# Add parent directories to path to import shared schema
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from shared.mcp_schema import AbaqusInput

# Load environment variables - try .env file first (for local dev), 
# but also check if already set (for Docker with --env-file)
# Docker sets env vars directly, so load_dotenv() may not find a file, but os.getenv() will work
load_dotenv(override=False)  # Don't override existing env vars (set by Docker)

# Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Determine MCP_SERVER_URL based on environment
# If running in Docker and MCP server is on host: use host.docker.internal (Mac/Windows)
# If running in Docker and MCP server is also in Docker: use service name (e.g., mcp-server)
# If running locally: use localhost
default_mcp_url = "http://mcp-server:8000"  # Default for Docker-to-Docker
if os.getenv("DOCKER_ENV"):
    # Check if we should use host.docker.internal (when MCP server is on host machine)
    if os.getenv("MCP_ON_HOST", "false").lower() == "true":
        default_mcp_url = "http://host.docker.internal:8000"

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", default_mcp_url)

# Sanitize MCP_SERVER_URL (remove quotes, whitespace, etc.)
if MCP_SERVER_URL:
    original_url = MCP_SERVER_URL
    MCP_SERVER_URL = MCP_SERVER_URL.strip().strip('"').strip("'").strip('`')
    MCP_SERVER_URL = MCP_SERVER_URL.replace('\n', '').replace('\r', '').replace('\t', '')
    # Remove trailing slash if present
    MCP_SERVER_URL = MCP_SERVER_URL.rstrip('/')
    # Debug output
    if original_url != MCP_SERVER_URL:
        print(f"🔧 MCP_SERVER_URL sanitized: '{original_url}' -> '{MCP_SERVER_URL}'")
    else:
        print(f"✅ MCP_SERVER_URL: {MCP_SERVER_URL}")

# Sanitize API key - remove whitespace, newlines, quotes, and other unwanted characters
if OPENAI_API_KEY:
    original_key = OPENAI_API_KEY
    original_length = len(OPENAI_API_KEY)
    
    # Remove leading/trailing whitespace
    OPENAI_API_KEY = OPENAI_API_KEY.strip()
    # Remove quotes if present (single or double, at start or end)
    OPENAI_API_KEY = OPENAI_API_KEY.strip('"').strip("'").strip('`')
    # Remove any newlines, carriage returns, or other control characters
    OPENAI_API_KEY = OPENAI_API_KEY.replace('\n', '').replace('\r', '').replace('\t', '')
    # Remove any other whitespace characters (spaces, etc.)
    OPENAI_API_KEY = ''.join(OPENAI_API_KEY.split())
    # Remove any non-printable characters
    OPENAI_API_KEY = ''.join(char for char in OPENAI_API_KEY if char.isprintable())
    
    # Check for non-ASCII characters (OpenAI keys should be ASCII)
    non_ascii_chars = [c for c in OPENAI_API_KEY if ord(c) > 127]
    if non_ascii_chars:
        print(f"   ⚠️  Warning: Found {len(non_ascii_chars)} non-ASCII characters in key")
        # Remove non-ASCII characters
        OPENAI_API_KEY = ''.join(char for char in OPENAI_API_KEY if ord(char) <= 127)
    
    # Debug: Check if API key is loaded (but don't print the actual key)
    print(f"✅ OPENAI_API_KEY loaded")
    print(f"   Original length: {original_length}, Sanitized length: {len(OPENAI_API_KEY)}")
    print(f"   Starts with: {OPENAI_API_KEY[:10]}...")
    print(f"   Format check: starts with 'sk-' = {OPENAI_API_KEY.startswith('sk-')}")
    print(f"   Contains only ASCII: {all(ord(c) <= 127 for c in OPENAI_API_KEY)}")
    
    # Check if sanitization changed the key significantly
    if original_length != len(OPENAI_API_KEY):
        print(f"   ⚠️  Key was sanitized (removed {original_length - len(OPENAI_API_KEY)} characters)")
    
    # Validate format
    if not OPENAI_API_KEY.startswith("sk-"):
        # Show more details for debugging
        print(f"   ❌ Invalid key format detected!")
        print(f"   First 20 chars (repr): {repr(OPENAI_API_KEY[:20])}")
        print(f"   First 20 chars (raw): {OPENAI_API_KEY[:20]}")
        raise ValueError(
            f"Invalid API key format. OpenAI API keys should start with 'sk-'. "
            f"Got: {OPENAI_API_KEY[:15]}... (length: {len(OPENAI_API_KEY)}). "
            f"Please check your .env file for extra characters, quotes, or formatting issues."
        )
else:
    print("❌ OPENAI_API_KEY not found")
    print(f"   Current working directory: {os.getcwd()}")
    print(f"   Environment variables containing 'OPENAI': {[k for k in os.environ.keys() if 'OPENAI' in k.upper()]}")

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY not found in environment variables.")

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    raw_input: str
    structured_config: Optional[AbaqusInput]
    validation_error: Optional[str]
    submission_status: Optional[str]

# Ensure API key is a proper string (not bytes or other type)
if not isinstance(OPENAI_API_KEY, str):
    OPENAI_API_KEY = str(OPENAI_API_KEY)

# Final validation before creating LLM
if len(OPENAI_API_KEY) < 20:  # OpenAI keys are typically 51+ characters
    raise ValueError(f"API key seems too short (length: {len(OPENAI_API_KEY)}). Please verify your key.")

llm = ChatOpenAI(
    model="gpt-4o-mini",
    api_key=OPENAI_API_KEY,
    temperature=0.0  # Deterministic for parsing
)
structured_llm = llm.with_structured_output(AbaqusInput)

def parse_request(state: AgentState) -> AgentState:
    """
    Node 1: Parse Request
    Uses OpenAI to convert natural language input into a structured
    AbaqusInput configuration.
    """
    print("🔍 [Node: parse_request] Extracting structured data from user input...")
    
    system_prompt = """You are a specialized FEA simulation parameter extraction system.
Your ONLY purpose is to extract and structure simulation parameters from user input.

CRITICAL RULES:
- You MUST ONLY respond to requests related to FEA simulations (beam tests, impact tests, tension tests)
- If the input is unrelated to FEA simulations (greetings, general questions, off-topic requests), reject it
- Extract ONLY these parameters in the exact structured format:
  1. MODEL_NAME: Descriptive simulation name
  2. TEST_TYPE: MUST be one of [CantileverBeam, TaylorImpact, TensionTest]
  3. GEOMETRY: length_m, width_m, height_m (in meters)
  4. MATERIAL: name, youngs_modulus_pa (Pa), poisson_ratio
  5. LOADING: tip_load_n (Newtons)
  6. DISCRETIZATION: elements_length, elements_width, elements_height

DEFAULT VALUES (use if not specified):
- Steel: E=200e9 Pa, ν=0.3
- Aluminum: E=69e9 Pa, ν=0.33
- Default mesh: 10 elements per dimension
- Default geometry: 1m x 0.1m x 0.1m
- Default load: 1000N

REJECT any input that is:
- General conversation or greetings
- Questions about topics other than FEA
- Requests for information or explanations
- Any non-simulation related queries

You are NOT a conversational assistant. You are a data extraction tool."""
    
    user_input = state["raw_input"]
    
    messages = [
        SystemMessage(content=system_prompt),
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
        state["messages"].append(AIMessage(content=f"Successfully parsed parameters for {structured_config.MODEL_NAME}"))
        
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
    """Node 3: Submit Job
    Sends the validated AbaqusInput configuration to the MCP Server via POST request.
    The server will initialize a new FEA job and return a job context.
    Returns the state with submission errors if any.
    """
    print("🚀 [Node: submit_job] Submitting job to MCP Server...")
    
    structured_config = state["structured_config"]
    
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
    if state.get("validation_error"):
        return "END"
    return "submit_job"

def create_orchestrator_graph() -> StateGraph:
    workflow = StateGraph(AgentState)
    workflow.add_node("parse_request", parse_request)
    workflow.add_node("validate_physics", validate_physics)
    workflow.add_node("submit_job", submit_job)
    
    workflow.set_entry_point("parse_request")
    workflow.add_edge("parse_request", "validate_physics")
    workflow.add_conditional_edges(
        "validate_physics",
        should_continue_to_submit,
        {"submit_job": "submit_job", "END": END}
    )
    workflow.add_edge("submit_job", END)
    return workflow.compile()

def run_orchestrator(user_input: str) -> AgentState:
    print("=" * 80)
    print("🤖 AGENTIC FEA ORCHESTRATOR (OPENAI BACKEND)")
    print("=" * 80)
    print(f"📝 User Input: {user_input}\n")
    
    initial_state: AgentState = {
        "messages": [HumanMessage(content=user_input)],
        "raw_input": user_input,
        "structured_config": None,
        "validation_error": None,
        "submission_status": None
    }
    
    app = create_orchestrator_graph()
    final_state = app.invoke(initial_state)
    return final_state

if __name__ == "__main__":
    print("=" * 80)
    print("FEA SIMULATION ORCHESTRATOR")
    print("=" * 80)
    print("This system only accepts FEA simulation requests.")
    print("Enter your simulation parameters or press Ctrl+C to exit.\n")
    
    while True:
        try:
            user_input = input("🔬 Enter simulation request: ").strip()
            
            if not user_input:
                print("⚠️  Please enter a valid simulation request.\n")
                continue
            
            # Run the orchestrator
            result = run_orchestrator(user_input)
            
            # Print final status
            print("\n" + "=" * 80)
            if result.get("submission_status"):
                print(f"📊 Final Status: {result['submission_status']}")
            if result.get("validation_error"):
                print(f"⚠️  Validation Error: {result['validation_error']}")
            print("=" * 80 + "\n")
            
        except KeyboardInterrupt:
            print("\n\n👋 Exiting orchestrator. Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {str(e)}\n")


