# models.py

from sqlalchemy import Column, String, DateTime, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class FEAJob(Base):
    """
    SQLAlchemy model for storing FEA job contexts.
    Uses JSONB for flexible storage of input parameters and logs.
    """
    __tablename__ = "fea_jobs"
    
    # Primary Key
    job_id = Column(String, primary_key=True, index=True)
    
    # Metadata
    job_name = Column(String, nullable=False, index=True)
    current_status = Column(String, nullable=False, index=True)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Flexible JSON storage for complex nested data
    input_parameters = Column(JSONB, nullable=False)
    logs = Column(JSONB, default=list, nullable=False)
    
    def __repr__(self):
        return f"<FEAJob(job_id={self.job_id}, job_name={self.job_name}, status={self.current_status})>"
