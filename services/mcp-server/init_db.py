#!/usr/bin/env python3
"""
Database initialization script.
Run this to create the database tables.
"""

from database import init_db

if __name__ == "__main__":
    print("=" * 50)
    print("FEA MCP Server - Database Initialization")
    print("=" * 50)
    init_db()
    print("\n✓ Database schema has been pushed successfully!")
    print("=" * 50)


