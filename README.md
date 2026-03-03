# Agentic Engineering Workflow Automation

## Prerequisites

- Docker image for Abaqus engine:
  - Available at: `ghcr.io/saasvidu/agentic-engineering-workflow-automation:abaqus-2024-v6`
  - The docker-compose file can be modified to use this image

- Azure Storage Account with a Blob Storage container:
  - Required for storing FEA job artifacts and data
  - Both MCP Server and FEA Worker services need access to this container
  - Configure via `AZURE_STORAGE_CONNECTION_STRING` and `AZURE_STORAGE_CONTAINER_NAME` environment variables

- A PostgreSQL database
  - Any provider
  - Could be hosted locally, or with a provider like Neon or Supabase for free

## Environment Variables

Each service requires a `.env` file. Copy the example files and fill in the values:

### Orchestrator (`services/orchestrator/.env`)
- `OPENAI_API_KEY` - OpenAI API key
- `MCP_SERVER_URL` - MCP server endpoint (e.g., `http://mcp_server:8000`)

### MCP Server (`services/mcp-server/.env`)
- `DATABASE_URL` - PostgreSQL connection string
- `AZURE_STORAGE_CONNECTION_STRING` - Azure Blob Storage connection string
- `AZURE_STORAGE_CONTAINER_NAME` - Blob container name
- `ARTIFACT_SAS_TTL_SECONDS` - SAS token TTL for artifacts

### FEA Worker (`services/fea-worker/.env`)
- `MCP_SERVER_URL` - MCP server endpoint (e.g., `http://mcp_server:8000`)
- `POLL_INTERVAL_SECONDS` - Job polling interval (e.g., 5)
- `ABAQUS_TIMEOUT_SECONDS` - Abaqus execution timeout (e.g., 1800)
- `ABAQUS_ENGINE_URL` - Abaqus engine API endpoint (e.g., `http://abaqus-engine:5000`)
- `AZURE_STORAGE_CONNECTION_STRING` - Azure Blob Storage connection string
- `AZURE_STORAGE_CONTAINER_NAME` - Blob container name

## Running the Application

Run the services using Docker Compose:

```bash
docker-compose -f docker-compose.orchestrator.yml up
docker-compose -f docker-compose.mcp-server.yml up
docker-compose -f docker-compose.fea-worker.yml up
```

**Frontend:** [agentic-engineering-workflow-automation-frontend](https://github.com/Saasvidu/agentic-engineering-workflow-automation-frontend)
