"""
Database configuration and session management for MCP server.
"""

import os
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from dotenv import load_dotenv
from models import Base

load_dotenv()


def sanitize_database_url(url: str) -> str:
    """
    Remove duplicate query parameters from database URL.
    
    Prevents errors when psycopg2 receives duplicate parameters.
    
    Args:
        url: Database URL string
        
    Returns:
        Sanitized URL string
    """
    parsed = urlparse(url)
    query_params = parse_qs(parsed.query, keep_blank_values=True)
    cleaned_params = {k: v[0] if isinstance(v, list) else v for k, v in query_params.items()}
    cleaned_query = urlencode(cleaned_params)
    
    return urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        cleaned_query,
        parsed.fragment
    ))


# ============================================================================
# Database Configuration
# ============================================================================

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set. Please configure it in your .env file.")

# Sanitize URL (remove quotes, whitespace, duplicate params)
DATABASE_URL = DATABASE_URL.strip().strip('"').strip("'").strip('`')
DATABASE_URL = DATABASE_URL.replace('\n', '').replace('\r', '').replace('\t', '')
DATABASE_URL = sanitize_database_url(DATABASE_URL)

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ============================================================================
# Database Functions
# ============================================================================

def get_db() -> Session:
    """
    FastAPI dependency to provide database sessions.
    
    Usage:
        db: Session = Depends(get_db)
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Initialize database by creating all tables."""
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully!")


if __name__ == "__main__":
    init_db()


