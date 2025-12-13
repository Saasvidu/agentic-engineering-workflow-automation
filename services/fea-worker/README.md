# FEA Worker Service

Worker agent that polls the MCP server for pending FEA jobs and executes Abaqus simulations.

## Overview

The FEA Worker is a background service that:

- Continuously polls MCP server for new jobs
- Prepares job directories and configuration files
- Executes Abaqus simulations
- Updates job status in MCP server

## Features

- Automatic job polling
- Abaqus simulation execution
- Job status tracking
- Error handling and logging

## Workflow

1. **Poll Queue** - Check MCP server for jobs with status `INITIALIZED`
2. **Acquire Job** - Mark job as `RUNNING`
3. **Prepare Directory** - Create job directory with config.json
4. **Execute Simulation** - Run Abaqus with simulation_runner.py
5. **Update Status** - Mark job as `COMPLETED` or `FAILED`

## Requirements

- Abaqus installation (for actual simulation execution)
- Access to MCP server API
- Python 3.11+

## Environment Variables

- `API_BASE_URL` - MCP server URL (default: `http://mcp-server:8000`)
- `ABAQUS_CMD_PATH` - Full path to Abaqus executable (required)
- `POLL_INTERVAL_SECONDS` - Polling interval in seconds (default: 5)

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
export API_BASE_URL="http://localhost:8000"
export ABAQUS_CMD_PATH="/path/to/abaqus.bat"  # Windows
# or
export ABAQUS_CMD_PATH="/usr/bin/abaqus"  # Linux

# Run worker
python fea_worker.py
```

## Running with Docker

**Note:** Abaqus typically requires host access or special Docker configuration.

```bash
docker build -t fea-worker -f Dockerfile ../..
docker run --env-file ../../.env fea-worker
```

For Abaqus access, you may need to:

- Mount Abaqus installation directory
- Use host networking mode
- Configure Abaqus licensing

## Job Directory Structure

Each job creates a directory:

```
jobs/
  {job_id}/
    config.json              # Job configuration
    simulation_runner.py      # Abaqus script
    abaqus_stdout.log         # Abaqus stdout
    abaqus_stderr.log         # Abaqus stderr
    [Abaqus output files]
```

## Simulation Runner

The `lib/simulation_runner.py` script is copied to each job directory and executed by Abaqus. It:

- Reads `config.json`
- Creates Abaqus model
- Generates mesh
- Sets up boundary conditions
- Submits analysis job

## Status Updates

The worker updates job status at key points:

- `RUNNING` - Job acquired and processing started
- `COMPLETED` - Simulation finished successfully
- `FAILED` - Simulation failed or error occurred

## Troubleshooting

### Worker not finding jobs

- Verify MCP server is running and accessible
- Check `API_BASE_URL` is correct
- Ensure jobs exist with status `INITIALIZED`

### Abaqus execution fails

- Verify `ABAQUS_CMD_PATH` points to correct executable
- Check Abaqus license is available
- Review `abaqus_stderr.log` in job directory

### Jobs stuck in RUNNING

- Check worker logs for errors
- Verify worker process is running
- Manually update job status via MCP API if needed

## Logs

Worker logs show:

- Polling status
- Job acquisition
- Simulation progress
- Status updates
- Errors


