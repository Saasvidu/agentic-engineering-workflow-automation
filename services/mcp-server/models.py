"""
SQLAlchemy database models for MCP server.

This module imports FEAJobContext from shared schema and provides conversion utilities.
The FEAJob model mirrors FEAJobContext but is optimized for database storage.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class FEAJob(Base):
    """
    SQLAlchemy model for storing FEA job contexts.
    
    Uses JSONB for flexible storage of input parameters and logs.
    Mirrors FEAJobContext structure but optimized for database storage.
    Use conversion utilities to convert between FEAJob and FEAJobContext.
    """
    __tablename__ = "fea_jobs"
    
    job_id = Column(String, primary_key=True, index=True)
    job_name = Column(String, nullable=False, index=True)
    current_status = Column(String, nullable=False, index=True)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    input_parameters = Column(JSONB, nullable=False)
    logs = Column(JSONB, default=list, nullable=False)
    
    def __repr__(self):
        return f"<FEAJob(job_id={self.job_id}, job_name={self.job_name}, status={self.current_status})>"


