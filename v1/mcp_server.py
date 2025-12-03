# mcp_server.py

from fastapi import FastAPI, HTTPException
from typing import Dict
from datetime import datetime
import uuid
from mcp_schema import FEAJobContext, AbaqusInput, FEAJobStatus

# 1. Initialize FastAPI Application
app = FastAPI(
    title="Model Context Protocol (MCP) Server v1",
    description="Central state management for Agentic FEA workflows.",
    version="1.0.0"
)

# 2. In-Memory Database (for the skeleton)
# In a production system, this would be a persistent database (e.g., Redis, Postgres).
# Key: job_id (str), Value: FEAJobContext object
job_store: Dict[str, FEAJobContext] = {}


# --- 3. Core MCP Endpoints (Phase 1 Deliverables) ---

@app.post("/mcp/init", response_model=FEAJobContext, status_code=201)
async def init_mcp(job_name: str, initial_input: AbaqusInput):
    """
    Initializes a new FEA simulation context. 
    The Orchestrator Agent calls this first, providing the user's initial config guess.
    """
    job_id = str(uuid.uuid4()) # Generate a globally unique identifier (UUID)
    
    # Create the initial job context object using the validated Pydantic models
    new_job = FEAJobContext(
        job_id=job_id,
        job_name=job_name,
        input_parameters=initial_input,
        # Status defaults to "INITIALIZED"
    )
    
    job_store[job_id] = new_job
    return new_job

@app.get("/mcp/{job_id}", response_model=FEAJobContext)
async def get_mcp_state(job_id: str):
    """
    Retrieves the current, authoritative state of a specific FEA job.
    All agents use this to READ the context.
    """
    if job_id not in job_store:
        raise HTTPException(status_code=404, detail=f"Job ID '{job_id}' not found.")
    return job_store[job_id]

@app.put("/mcp/{job_id}/status", response_model=FEAJobContext)
async def update_mcp_status(job_id: str, new_status: FEAJobStatus, log_message: str):
    """
    Allows an Agent to update ONLY the job status and add a log entry.
    """
    if job_id not in job_store:
        raise HTTPException(status_code=404, detail=f"Job ID '{job_id}' not found.")
    
    job_context = job_store[job_id]
    
    # Update the critical fields
    job_context.current_status = new_status
    job_context.last_updated = datetime.utcnow()
    job_context.logs.append(f"[{job_context.last_updated.isoformat()}] Agent Action: {log_message} (New Status: {new_status})")
    
    return job_context

@app.get("/mcp/queue/next", response_model=Optional[FEAJobContext])
async def get_next_pending_job():
    """
    Worker Agents call this loop to find work.
    Logic: Returns the first job found with status 'INITIALIZED'.
    Returns null/None if queue is empty.
    """
    for job in job_store.values():
        if job.current_status == "INITIALIZED":
            return job
    return None