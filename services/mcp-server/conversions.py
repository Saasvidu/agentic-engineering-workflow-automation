# conversions.py
"""
Utility functions for converting between FEAJobContext (Pydantic) and FEAJob (SQLAlchemy).
This module provides clean conversion functions to eliminate manual conversion code.
"""

import sys
from pathlib import Path

# Add parent directories to path to import shared schema
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.mcp_schema import FEAJobContext, AbaqusInput
from models import FEAJob


def pydantic_to_db(pydantic_job: FEAJobContext) -> FEAJob:
    """
    Convert FEAJobContext (Pydantic) to FEAJob (SQLAlchemy) for database storage.
    
    Args:
        pydantic_job: The Pydantic FEAJobContext instance
        
    Returns:
        FEAJob SQLAlchemy instance ready for database operations
    """
    return FEAJob(
        job_id=pydantic_job.job_id,
        job_name=pydantic_job.job_name,
        current_status=pydantic_job.current_status,
        last_updated=pydantic_job.last_updated,
        input_parameters=pydantic_job.input_parameters.model_dump(),
        logs=pydantic_job.logs
    )


def db_to_pydantic(db_job: FEAJob) -> FEAJobContext:
    """
    Convert FEAJob (SQLAlchemy) to FEAJobContext (Pydantic) for API responses.
    
    Args:
        db_job: The SQLAlchemy FEAJob instance from database
        
    Returns:
        FEAJobContext Pydantic instance ready for API serialization
    """
    return FEAJobContext(
        job_id=db_job.job_id,
        job_name=db_job.job_name,
        current_status=db_job.current_status,
        last_updated=db_job.last_updated,
        input_parameters=AbaqusInput(**db_job.input_parameters),
        logs=db_job.logs
    )

