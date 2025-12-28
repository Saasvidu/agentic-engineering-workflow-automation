# mcp_server.py

from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
import uuid
import sys
from pathlib import Path

# Add parent directories to path to import shared schema
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from shared.mcp_schema import FEAJobContext, AbaqusInput, FEAJobStatus
from database import get_db, init_db
from models import FEAJob
from conversions import pydantic_to_db, db_to_pydantic

# 1. Initialize FastAPI Application
app = FastAPI(
    title="Model Context Protocol (MCP) Server v1",
    description="Central state management for Agentic FEA workflows.",
    version="1.0.0"
)

# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    init_db()


# --- 3. Core MCP Endpoints (Phase 1 Deliverables) ---

@app.post("/mcp/init", response_model=FEAJobContext, status_code=201)
async def init_mcp(job_name: str, initial_input: AbaqusInput, db: Session = Depends(get_db)):
    """
    Initializes a new FEA simulation context. 
    The Orchestrator Agent calls this first, providing the user's initial config guess.
    """
    job_id = str(uuid.uuid4()) # Generate a globally unique identifier (UUID)
    
    # Create the Pydantic model (single source of truth)
    new_job = FEAJobContext(
        job_id=job_id,
        job_name=job_name,
        input_parameters=initial_input,
        # Status defaults to "INITIALIZED"
    )
    
    # Convert to SQLAlchemy model and store in database
    db_job = pydantic_to_db(new_job)
    db.add(db_job)
    db.commit()
    db.refresh(db_job)
    
    # Convert back to Pydantic for response
    return db_to_pydantic(db_job)

@app.get("/mcp/{job_id}", response_model=FEAJobContext)
async def get_mcp_state(job_id: str, db: Session = Depends(get_db)):
    """
    Retrieves the current, authoritative state of a specific FEA job.
    All agents use this to READ the context.
    """
    db_job = db.query(FEAJob).filter(FEAJob.job_id == job_id).first()
    
    if not db_job:
        raise HTTPException(status_code=404, detail=f"Job ID '{job_id}' not found.")
    
    # Convert SQLAlchemy model to Pydantic model
    return db_to_pydantic(db_job)

@app.put("/mcp/{job_id}/status", response_model=FEAJobContext)
async def update_mcp_status(job_id: str, new_status: FEAJobStatus, log_message: str, db: Session = Depends(get_db)):
    """
    Allows an Agent to update ONLY the job status and add a log entry.
    """
    db_job = db.query(FEAJob).filter(FEAJob.job_id == job_id).first()
    
    if not db_job:
        raise HTTPException(status_code=404, detail=f"Job ID '{job_id}' not found.")
    
    # Update the critical fields on the SQLAlchemy model
    db_job.current_status = new_status
    db_job.last_updated = datetime.utcnow()
    
    # Append to logs
    logs = db_job.logs if db_job.logs else []
    logs.append(f"[{db_job.last_updated.isoformat()}] Agent Action: {log_message} (New Status: {new_status})")
    db_job.logs = logs
    
    db.commit()
    db.refresh(db_job)
    
    # Convert to Pydantic model for response
    return db_to_pydantic(db_job)

@app.get("/mcp/queue/next", response_model=Optional[FEAJobContext])
async def get_next_pending_job(db: Session = Depends(get_db)):
    """
    Worker Agents call this loop to find work.
    Logic: Returns the first job found with status 'INITIALIZED'.
    Returns null/None if queue is empty.
    """
    db_job = db.query(FEAJob).filter(FEAJob.current_status == "INITIALIZED").first()
    
    if not db_job:
        return None
    
    # Convert to Pydantic model
    return db_to_pydantic(db_job)


