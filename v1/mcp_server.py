# mcp_server.py

from fastapi import FastAPI, HTTPException
from typing import Dict
from datetime import datetime
import uuid
from mcp_schema import ModelContextProtocol, AbaqusInput, FEAJobStatus

# 1. Initialize FastAPI Application
app = FastAPI(
    title="Model Context Protocol (MCP) Server v1",
    description="Central state management for Agentic FEA workflows.",
    version="1.0.0"
)

# 2. In-Memory Database (for the skeleton)
# In a production system, this would be a persistent database (e.g., Redis, Postgres).
# Key: mcp_id (str), Value: ModelContextProtocol object
mcp_store: Dict[str, ModelContextProtocol] = {}


# --- 3. Core MCP Endpoints (Phase 1 Deliverables) ---

@app.post("/mcp/init", response_model=ModelContextProtocol, status_code=201)
async def init_mcp(job_name: str, initial_input: AbaqusInput):
    """
    Initializes a new FEA simulation context. 
    The Orchestrator Agent calls this first, providing the user's initial config guess.
    """
    mcp_id = str(uuid.uuid4()) # Generate a globally unique identifier (UUID)
    
    # Create the initial MCP object using the validated Pydantic models
    new_mcp = ModelContextProtocol(
        mcp_id=mcp_id,
        job_name=job_name,
        input_parameters=initial_input,
        # Status defaults to "INITIALIZED"
    )
    
    mcp_store[mcp_id] = new_mcp
    return new_mcp

@app.get("/mcp/{mcp_id}", response_model=ModelContextProtocol)
async def get_mcp_state(mcp_id: str):
    """
    Retrieves the current, authoritative state of a specific FEA job.
    All agents use this to READ the context.
    """
    if mcp_id not in mcp_store:
        raise HTTPException(status_code=404, detail=f"MCP ID '{mcp_id}' not found.")
    return mcp_store[mcp_id]

@app.put("/mcp/{mcp_id}/status", response_model=ModelContextProtocol)
async def update_mcp_status(mcp_id: str, new_status: FEAJobStatus, log_message: str):
    """
    Allows an Agent to update ONLY the job status and add a log entry.
    """
    if mcp_id not in mcp_store:
        raise HTTPException(status_code=404, detail=f"MCP ID '{mcp_id}' not found.")
    
    mcp = mcp_store[mcp_id]
    
    # Update the critical fields
    mcp.current_status = new_status
    mcp.last_updated = datetime.utcnow()
    mcp.logs.append(f"[{mcp.last_updated.isoformat()}] Agent Action: {log_message} (New Status: {new_status})")
    
    return mcp