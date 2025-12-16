# database.py

import os
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from dotenv import load_dotenv
from models import Base

# Load environment variables from .env file
load_dotenv()

def sanitize_database_url(url: str) -> str:
    """
    Remove duplicate query parameters from database URL.
    This prevents errors when psycopg2 receives duplicate parameters like channel_binding.
    """
    parsed = urlparse(url)
    query_params = parse_qs(parsed.query, keep_blank_values=True)
    
    # Remove duplicates by keeping only the first occurrence of each parameter
    # parse_qs returns lists, so we take the first value
    cleaned_params = {k: v[0] if isinstance(v, list) else v for k, v in query_params.items()}
    
    # Reconstruct the URL
    cleaned_query = urlencode(cleaned_params)
    return urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        cleaned_query,
        parsed.fragment
    ))

# Get DATABASE_URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set. Please configure it in your .env file.")

# Sanitize the URL: remove quotes, whitespace, etc. (common in .env files)
DATABASE_URL = DATABASE_URL.strip().strip('"').strip("'").strip('`')
DATABASE_URL = DATABASE_URL.replace('\n', '').replace('\r', '').replace('\t', '')

# Sanitize the URL to remove duplicate query parameters
DATABASE_URL = sanitize_database_url(DATABASE_URL)

# Create SQLAlchemy engine
engine = create_engine(DATABASE_URL, echo=False)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db() -> Session:
    """
    Dependency function for FastAPI to provide database sessions.
    Usage: db: Session = Depends(get_db)
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """
    Initialize the database by creating all tables.
    Call this once during application startup or as a separate setup step.
    """
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully!")

if __name__ == "__main__":
    # Allow running this file directly to initialize the database
    init_db()


