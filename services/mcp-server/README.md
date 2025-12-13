# MCP Server

Model Context Protocol (MCP) Server - Central state management API for Agentic FEA workflows.

## Overview

The MCP Server is a FastAPI-based REST API that manages FEA job state and provides a centralized interface for orchestrator and worker agents to coordinate simulation workflows.

## Features

- Job initialization and state management
- PostgreSQL database for persistent storage
- RESTful API endpoints
- Job queue management for worker agents

## API Endpoints

### Initialize Job

```http
POST /mcp/init?job_name={job_name}
Content-Type: application/json

{
  "MODEL_NAME": "beam1",
  "TEST_TYPE": "CantileverBeam",
  "GEOMETRY": {
    "length_m": 1.0,
    "width_m": 0.1,
    "height_m": 0.1
  },
  "MATERIAL": {
    "name": "Steel",
    "youngs_modulus_pa": 200000000000.0,
    "poisson_ratio": 0.3
  },
  "LOADING": {
    "tip_load_n": 1000.0
  },
  "DISCRETIZATION": {
    "elements_length": 10,
    "elements_width": 4,
    "elements_height": 4
  }
}
```

**Response:** `201 Created`

```json
{
  "job_id": "uuid-here",
  "job_name": "beam1",
  "current_status": "INITIALIZED",
  "last_updated": "2024-01-01T00:00:00",
  "input_parameters": { ... },
  "logs": []
}
```

### Get Job State

```http
GET /mcp/{job_id}
```

**Response:** `200 OK`

```json
{
  "job_id": "uuid-here",
  "job_name": "beam1",
  "current_status": "RUNNING",
  "last_updated": "2024-01-01T00:00:00",
  "input_parameters": { ... },
  "logs": ["[timestamp] Agent Action: ..."]
}
```

### Update Job Status

```http
PUT /mcp/{job_id}/status?new_status={status}&log_message={message}
```

**Status values:** `INITIALIZED`, `INPUT_GENERATED`, `MESHING_STARTED`, `RUNNING`, `COMPLETED`, `FAILED`

**Response:** `200 OK` - Updated job context

### Get Next Pending Job

```http
GET /mcp/queue/next
```

**Response:** `200 OK` - Job context or `null` if queue is empty

## Environment Variables

- `DATABASE_URL` - PostgreSQL connection string (required)
- `PORT` - Server port (default: 8000)

## Database Schema

### FEAJob Table

- `job_id` (String, Primary Key)
- `job_name` (String)
- `current_status` (String)
- `last_updated` (DateTime)
- `input_parameters` (JSONB)
- `logs` (JSONB)

## Running Locally

**Prerequisites:** Install `uv` first:

- Linux/Mac: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Windows: `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`

```bash
# Setup virtual environment and install dependencies
./setup.sh  # or setup.ps1 on Windows

# Activate virtual environment
source .venv/bin/activate  # On Windows: .venv\Scripts\Activate.ps1

# Set environment variables
export DATABASE_URL="postgresql://user:password@localhost:5432/fea_db"

# Initialize database
python init_db.py

# Run server
uvicorn mcp_server:app --reload
```

## Running with Docker

```bash
docker build -t mcp-server -f Dockerfile ../..
docker run -p 8000:8000 --env-file ../../.env mcp-server
```

## API Documentation

Interactive API documentation available at:

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc


