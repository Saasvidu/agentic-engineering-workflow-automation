"""
MCP Server - Central state management API for Agentic FEA workflows.

Provides REST API endpoints for job initialization, status updates, and queue management.
"""

from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
import uuid
import sys
import os
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from shared.mcp_schema import FEAJobContext, AbaqusInput, FEAJobStatus
from database import get_db, init_db
from models import FEAJob
from conversions import pydantic_to_db, db_to_pydantic
from azure_artifacts import build_artifact_urls, ArtifactUrlsResponse
from azure.core.exceptions import AzureError

logger = logging.getLogger(__name__)

# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title="Model Context Protocol (MCP) Server v1",
    description="Central state management for Agentic FEA workflows.",
    version="1.0.0"
)


@app.on_event("startup")
async def startup_event():
    """Initialize database tables on application startup."""
    init_db()


# ============================================================================
# MCP API Endpoints
# ============================================================================

@app.post("/mcp/init", response_model=FEAJobContext, status_code=201)
async def init_mcp(job_name: str, initial_input: AbaqusInput, db: Session = Depends(get_db)):
    """
    Initialize a new FEA simulation context.
    
    Args:
        job_name: User-provided job identifier
        initial_input: Validated Abaqus input configuration
        db: Database session
        
    Returns:
        Created FEAJobContext with generated job_id
    """
    job_id = str(uuid.uuid4())
    
    new_job = FEAJobContext(
        job_id=job_id,
        job_name=job_name,
        input_parameters=initial_input
    )
    
    db_job = pydantic_to_db(new_job)
    db.add(db_job)
    db.commit()
    db.refresh(db_job)
    
    return db_to_pydantic(db_job)

@app.get("/mcp/{job_id}", response_model=FEAJobContext)
async def get_mcp_state(job_id: str, db: Session = Depends(get_db)):
    """
    Retrieve the current state of a specific FEA job.
    
    Args:
        job_id: Unique job identifier
        db: Database session
        
    Returns:
        FEAJobContext for the requested job
        
    Raises:
        HTTPException: If job not found
    """
    db_job = db.query(FEAJob).filter(FEAJob.job_id == job_id).first()
    
    if not db_job:
        raise HTTPException(status_code=404, detail=f"Job ID '{job_id}' not found.")
    
    return db_to_pydantic(db_job)


@app.put("/mcp/{job_id}/status", response_model=FEAJobContext)
async def update_mcp_status(
    job_id: str,
    new_status: FEAJobStatus,
    log_message: str,
    db: Session = Depends(get_db)
):
    """
    Update job status and add log entry.
    
    Args:
        job_id: Unique job identifier
        new_status: New status to set
        log_message: Log message to record
        db: Database session
        
    Returns:
        Updated FEAJobContext
        
    Raises:
        HTTPException: If job not found
    """
    db_job = db.query(FEAJob).filter(FEAJob.job_id == job_id).first()
    
    if not db_job:
        raise HTTPException(status_code=404, detail=f"Job ID '{job_id}' not found.")
    
    db_job.current_status = new_status
    db_job.last_updated = datetime.utcnow()
    
    logs = db_job.logs if db_job.logs else []
    logs.append(f"[{db_job.last_updated.isoformat()}] Agent Action: {log_message} (New Status: {new_status})")
    db_job.logs = logs
    
    db.commit()
    db.refresh(db_job)
    
    return db_to_pydantic(db_job)


@app.get("/mcp/queue/next", response_model=Optional[FEAJobContext])
async def get_next_pending_job(db: Session = Depends(get_db)):
    """
    Get the next pending job from the queue.
    
    Returns the first job with status 'INITIALIZED', or None if queue is empty.
    
    Args:
        db: Database session
        
    Returns:
        FEAJobContext if job available, None otherwise
    """
    db_job = db.query(FEAJob).filter(FEAJob.current_status == "INITIALIZED").first()
    
    if not db_job:
        return None
    
    return db_to_pydantic(db_job)


@app.get("/mcp/{job_id}/artifacts", response_model=ArtifactUrlsResponse)
async def get_job_artifacts(job_id: str, db: Session = Depends(get_db)):
    """
    Get time-limited, read-only SAS URLs for job artifacts stored in Azure Blob Storage.
    
    Args:
        job_id: Unique job identifier
        db: Database session
        
    Returns:
        ArtifactUrlsResponse containing signed URLs for:
        - summary.json
        - data/preview.png
        - data/mesh.glb
        - data/mesh.vtu
        
    Raises:
        HTTPException: 404 if job not found, 500 if Azure configuration or SDK errors occur
    """
    # Validate job exists
    db_job = db.query(FEAJob).filter(FEAJob.job_id == job_id).first()
    
    if not db_job:
        logger.warning(f"Artifact request for non-existent job: {job_id}")
        raise HTTPException(status_code=404, detail=f"Job ID '{job_id}' not found.")
    
    # Get TTL from environment (default 3600 seconds)
    ttl_seconds = int(os.getenv("ARTIFACT_SAS_TTL_SECONDS", "3600"))
    
    try:
        # Generate signed URLs for artifacts
        artifact_urls = build_artifact_urls(job_id, ttl_seconds=ttl_seconds)
        
        logger.info(f"Successfully generated artifact URLs for job {job_id}")
        
        return ArtifactUrlsResponse(
            job_id=job_id,
            expires_in_seconds=ttl_seconds,
            base_path=f"{job_id}/",
            artifacts=artifact_urls
        )
        
    except ValueError as e:
        # Missing Azure configuration
        logger.error(f"Azure configuration error for job {job_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Azure Storage is not configured. Cannot generate artifact URLs. Error: {str(e)}"
        )
    except AzureError as e:
        # Azure SDK errors
        logger.error(f"Azure SDK error for job {job_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate artifact URLs due to Azure Storage error: {str(e)}"
        )
    except Exception as e:
        # Unexpected errors
        logger.error(f"Unexpected error generating artifact URLs for job {job_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error while generating artifact URLs: {str(e)}"
        )

