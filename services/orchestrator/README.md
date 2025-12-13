# Orchestrator Service

AI-powered orchestrator for parsing natural language FEA simulation requests and submitting them to the MCP server.

## Overview

The Orchestrator service combines:

- **LangGraph-based AI agent** - Parses and validates simulation requests
- **Streamlit web UI** - User-friendly chatbot interface

## Features

- Natural language processing for simulation requests
- Physics parameter validation
- Structured data extraction using OpenAI GPT-4o-mini
- Web-based chat interface

## Workflow

1. **Parse Request** - Extract structured parameters from natural language
2. **Validate Physics** - Check engineering constraints
3. **Submit Job** - Send validated config to MCP server

## Supported Test Types

- `CantileverBeam` - Cantilever beam analysis
- `TaylorImpact` - Taylor impact test
- `TensionTest` - Tension test

## Usage

### Web UI (Streamlit)

1. Start the service: `streamlit run streamlit_app.py`
2. Open browser: http://localhost:8501
3. Enter simulation request in chat

**Example Input:**

```
Create a cantilever beam test with steel material, 1m length, 1000N tip load
```

### Command Line

```bash
python orchestrator.py
```

Then enter simulation requests interactively.

## Environment Variables

- `OPENAI_API_KEY` - OpenAI API key (required)
- `MCP_SERVER_URL` - MCP server URL (default: `http://mcp-server:8000`)

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
export OPENAI_API_KEY="your-api-key"
export MCP_SERVER_URL="http://localhost:8000"

# Run Streamlit UI
streamlit run streamlit_app.py

# Or run CLI version
python orchestrator.py
```

## Running with Docker

```bash
docker build -t orchestrator -f Dockerfile ../..
docker run -p 8501:8501 --env-file ../../.env orchestrator
```

## Architecture

- Uses LangGraph for workflow orchestration
- OpenAI GPT-4o-mini for structured output extraction
- Pydantic models for validation
- Streamlit for UI

## Example Output

```
✅ Job submitted successfully!
   Job ID: abc-123-def
   Job Name: beam1
   Status: INITIALIZED

Configuration Details:
- Model: beam1
- Test Type: CantileverBeam
- Material: Steel
- Geometry: 1.0m × 0.1m × 0.1m
```


