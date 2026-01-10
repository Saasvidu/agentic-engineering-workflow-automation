"""
MCP Server - Central state management API for Agentic FEA workflows.

Provides REST API endpoints for job initialization, status updates, and queue management.
"""

from fastapi import FastAPI, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel
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
# Response Models
# ============================================================================

class JobListItem(BaseModel):
    """Minimal job information for listing."""
    job_id: str
    job_name: str
    current_status: str
    last_updated: datetime

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class JobListResponse(BaseModel):
    """Paginated job list response."""
    items: List[JobListItem]
    limit: int
    has_more: bool
    next_cursor: Optional[str] = None


# ============================================================================
# Cursor Helper Functions
# ============================================================================

def encode_cursor(last_updated: datetime, job_id: str) -> str:
    """
    Encode a cursor from datetime and job_id.
    
    Args:
        last_updated: Last updated timestamp
        job_id: Job identifier
        
    Returns:
        Opaque cursor string in format "{iso_datetime}|{job_id}"
    """
    return f"{last_updated.isoformat()}|{job_id}"


def decode_cursor(cursor: str) -> tuple[datetime, str]:
    """
    Decode a cursor string into datetime and job_id.
    
    Args:
        cursor: Cursor string in format "{iso_datetime}|{job_id}"
        
    Returns:
        Tuple of (datetime, job_id)
        
    Raises:
        ValueError: If cursor format is invalid
    """
    parts = cursor.split("|", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid cursor format. Expected 'datetime|job_id', got: {cursor}")
    
    iso_datetime_str, job_id = parts
    
    try:
        cursor_dt = datetime.fromisoformat(iso_datetime_str)
    except ValueError as e:
        raise ValueError(f"Invalid datetime in cursor: {iso_datetime_str}") from e
    
    return cursor_dt, job_id


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

@app.get("/mcp/jobs", response_model=JobListResponse)
async def list_jobs(
    limit: int = Query(20, ge=1, le=100, description="Number of jobs to return (1-100)"),
    cursor: Optional[str] = Query(None, description="Pagination cursor from previous response"),
    status: Optional[FEAJobStatus] = Query(None, description="Filter by job status"),
    db: Session = Depends(get_db)
):
    """
    List FEA jobs with cursor-based pagination.
    
    Returns jobs ordered by last_updated DESC, job_id DESC.
    Supports optional status filtering and cursor-based pagination.
    
    Args:
        limit: Maximum number of jobs to return (1-100, default 20)
        cursor: Opaque pagination cursor from previous response
        status: Optional status filter (e.g., COMPLETED, FAILED, RUNNING)
        db: Database session
        
    Returns:
        JobListResponse with paginated job items
        
    Raises:
        HTTPException: 400 if cursor format is invalid
    """
    # Decode cursor if provided
    cursor_dt = None
    cursor_job_id = None
    if cursor:
        try:
            cursor_dt, cursor_job_id = decode_cursor(cursor)
        except ValueError as e:
            logger.warning(f"Invalid cursor format: {cursor} - {e}")
            raise HTTPException(
                status_code=400,
                detail=f"Invalid cursor format: {str(e)}"
            )
    
    # Build query
    query = db.query(FEAJob)
    
    # Apply status filter if provided
    if status:
        query = query.filter(FEAJob.current_status == status)
    
    # Apply cursor filter if provided
    if cursor_dt is not None and cursor_job_id is not None:
        # Return jobs where:
        # - last_updated < cursor_dt
        # OR
        # - last_updated == cursor_dt AND job_id < cursor_job_id
        query = query.filter(
            or_(
                FEAJob.last_updated < cursor_dt,
                and_(
                    FEAJob.last_updated == cursor_dt,
                    FEAJob.job_id < cursor_job_id
                )
            )
        )
    
    # Order by last_updated DESC, job_id DESC
    query = query.order_by(FEAJob.last_updated.desc(), FEAJob.job_id.desc())
    
    # Fetch limit + 1 to determine if there are more pages
    results = query.limit(limit + 1).all()
    
    # Determine if there are more pages
    has_more = len(results) > limit
    
    # Slice to actual limit
    items = results[:limit]
    
    # Build response items
    job_items = [
        JobListItem(
            job_id=job.job_id,
            job_name=job.job_name,
            current_status=job.current_status,
            last_updated=job.last_updated
        )
        for job in items
    ]
    
    # Encode next cursor if there are more pages
    next_cursor = None
    if has_more and items:
        last_job = items[-1]
        next_cursor = encode_cursor(last_job.last_updated, last_job.job_id)
    
    return JobListResponse(
        items=job_items,
        limit=limit,
        has_more=has_more,
        next_cursor=next_cursor
    )


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


