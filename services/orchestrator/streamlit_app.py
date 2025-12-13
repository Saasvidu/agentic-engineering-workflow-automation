"""
Streamlit UI for FEA Simulation Orchestrator
A chatbot interface that wraps the orchestrator backend logic.
"""

import os
import streamlit as st
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables early (before importing orchestrator)
# This ensures env vars are available when orchestrator module loads
load_dotenv(override=False)  # Don't override if already set (Docker sets them directly)

# Add parent directories to path to import orchestrator and shared schema
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from orchestrator import run_orchestrator
from langchain_core.messages import AIMessage

# Page configuration
st.set_page_config(
    page_title="FEA Simulation Orchestrator",
    page_icon="🔬",
    layout="wide"
)

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []

if "processing" not in st.session_state:
    st.session_state.processing = False

# Title and description
st.title("🔬 FEA Simulation Orchestrator")
st.markdown("""
This system accepts FEA simulation requests for:
- **CantileverBeam** tests
- **TaylorImpact** tests  
- **TensionTest** tests

Enter your simulation parameters in natural language below.
""")

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Chat input
if prompt := st.chat_input("Enter your simulation request..."):
    # Add user message to chat
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    
    # Process the request
    with st.chat_message("assistant"):
        with st.spinner("Processing simulation request..."):
            try:
                # Run the orchestrator with the user's input
                result = run_orchestrator(prompt)
                
                # Extract response from the result
                response_parts = []
                
                # Get the last AI message from the orchestrator
                if result.get("messages"):
                    # Find the last AI message
                    last_ai_msg = None
                    for msg in reversed(result["messages"]):
                        if isinstance(msg, AIMessage):
                            try:
                                content = msg.content
                                if content and isinstance(content, str):
                                    last_ai_msg = content
                                    break
                            except:
                                pass
                    
                    if last_ai_msg:
                        response_parts.append(last_ai_msg)
                
                # Add structured config info if available
                if result.get("structured_config"):
                    config = result["structured_config"]
                    response_parts.append(f"\n**Configuration Details:**")
                    response_parts.append(f"- Model: {config.MODEL_NAME}")
                    response_parts.append(f"- Test Type: {config.TEST_TYPE}")
                    response_parts.append(f"- Material: {config.MATERIAL.name}")
                    if hasattr(config, 'GEOMETRY'):
                        geo = config.GEOMETRY
                        response_parts.append(f"- Geometry: {geo.length_m}m × {geo.width_m}m × {geo.height_m}m")
                
                # Add submission status
                if result.get("submission_status"):
                    status = result["submission_status"]
                    if status.startswith("SUCCESS"):
                        response_parts.append(f"\n✅ **{status}**")
                    else:
                        response_parts.append(f"\n❌ **{status}**")
                
                # Add validation error if present
                if result.get("validation_error"):
                    response_parts.append(f"\n⚠️ **Validation Error:** {result['validation_error']}")
                
                # Combine all response parts
                response = "\n".join(response_parts) if response_parts else "Processing complete."
                
                st.markdown(response)
                
                # Add assistant response to chat history
                st.session_state.messages.append({"role": "assistant", "content": response})
                
            except Exception as e:
                error_msg = f"❌ Error processing request: {str(e)}"
                st.error(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})

# Sidebar with additional info
with st.sidebar:
    st.header("ℹ️ About")
    st.markdown("""
    This orchestrator processes FEA simulation requests and:
    
    1. **Parses** your natural language input
    2. **Validates** the physics parameters
    3. **Submits** the job to the MCP server
    
    **Supported Test Types:**
    - CantileverBeam
    - TaylorImpact
    - TensionTest
    
    **Example Input:**
    "Create a cantilever beam test with steel material, 1m length, 1000N tip load"
    """)
    
    if st.button("Clear Chat History"):
        st.session_state.messages = []
        st.rerun()


