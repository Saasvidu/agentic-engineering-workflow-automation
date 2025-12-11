# Agentic Engineering Workflow Automation

A distributed microservices system for automating FEA (Finite Element Analysis) simulation workflows using AI orchestration.

## Architecture Overview

This system is organized as a monorepo with three independent microservices:

```
agentic-engineering-workflow-automation/
├── services/
│   ├── mcp-server/          # MCP API Server + Database Layer
│   ├── orchestrator/         # Orchestrator + Streamlit UI
│   └── fea-worker/           # FEA Worker Agent
├── shared/                   # Shared code (schemas, utilities)
│   └── mcp_schema.py
├── docker-compose.yml        # Local development orchestration
└── .env.example             # Environment variable templates
```

### Services

1. **MCP Server** (`services/mcp-server/`)

   - FastAPI REST API server
   - PostgreSQL database for job state management
   - Central state management for FEA workflows
   - Port: 8000

2. **Orchestrator** (`services/orchestrator/`)

   - LangGraph-based AI agent
   - Parses natural language simulation requests
   - Validates physics parameters
   - Streamlit web UI for user interaction
   - Port: 8501

3. **FEA Worker** (`services/fea-worker/`)
   - Polls MCP server for pending jobs
   - Executes Abaqus simulations
   - Updates job status
   - No exposed ports (internal service)

## Quick Start

### Prerequisites

- Docker and Docker Compose installed
- OpenAI API key (for orchestrator)
- Abaqus installation (for FEA worker, optional for testing)

### Setup

1. **Clone the repository**

   ```bash
   git clone <repository-url>
   cd agentic-engineering-workflow-automation
   ```

2. **Configure environment variables**

   ```bash
   cp .env.example .env
   # Edit .env and fill in required values:
   # - OPENAI_API_KEY (required)
   # - ABAQUS_CMD_PATH (optional, for FEA worker)
   ```

3. **Start all services with Docker Compose**

   ```bash
   docker-compose up --build
   ```

4. **Access the services**
   - Streamlit UI: http://localhost:8501
   - MCP Server API: http://localhost:8000
   - API Documentation: http://localhost:8000/docs

### Running Services Individually

#### MCP Server

```bash
cd services/mcp-server
docker build -t mcp-server -f Dockerfile ../..
docker run -p 8000:8000 --env-file ../../.env mcp-server
```

#### Orchestrator

```bash
cd services/orchestrator
docker build -t orchestrator -f Dockerfile ../..
docker run -p 8501:8501 --env-file ../../.env orchestrator
```

#### FEA Worker

```bash
cd services/fea-worker
docker build -t fea-worker -f Dockerfile ../..
docker run --env-file ../../.env fea-worker
```

## Development Workflow

### Local Development (Without Docker)

**Prerequisites:** Install `uv` first:

- Linux/Mac: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Windows: `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`

1. **Set up all services at once (recommended)**

   ```bash
   # Linux/Mac
   ./setup-all.sh

   # Windows PowerShell
   .\setup-all.ps1
   ```

   Or set up each service individually:

   ```bash
   # MCP Server
   cd services/mcp-server
   ./setup.sh  # or setup.ps1 on Windows
   source .venv/bin/activate  # On Windows: .venv\Scripts\Activate.ps1

   # Orchestrator
   cd ../orchestrator
   ./setup.sh  # or setup.ps1 on Windows
   source .venv/bin/activate  # On Windows: .venv\Scripts\Activate.ps1

   # FEA Worker
   cd ../fea-worker
   ./setup.sh  # or setup.ps1 on Windows
   source .venv/bin/activate  # On Windows: .venv\Scripts\Activate.ps1
   ```

   Each service now has its own `.venv` virtual environment managed by `uv`.

2. **Set up PostgreSQL database**

   - Install PostgreSQL locally or use Docker:
     ```bash
     docker run -d --name postgres -e POSTGRES_PASSWORD=fea_password -e POSTGRES_DB=fea_db -p 5432:5432 postgres:15-alpine
     ```

3. **Configure environment variables**

   - Update `.env` with local development URLs:
     ```
     DATABASE_URL=postgresql://fea_user:fea_password@localhost:5432/fea_db
     MCP_SERVER_URL=http://localhost:8000
     API_BASE_URL=http://localhost:8000
     ```

4. **Run services**

   ```bash
   # Terminal 1: MCP Server
   cd services/mcp-server
   uvicorn mcp_server:app --reload

   # Terminal 2: Orchestrator
   cd services/orchestrator
   streamlit run streamlit_app.py

   # Terminal 3: FEA Worker
   cd services/fea-worker
   python fea_worker.py
   ```

## Service Communication

Services communicate via REST APIs:

- **Orchestrator → MCP Server**: Job submission (`POST /mcp/init`)
- **FEA Worker → MCP Server**: Job polling (`GET /mcp/queue/next`), status updates (`PUT /mcp/{job_id}/status`)

In Docker Compose, services discover each other via service names:

- `http://mcp-server:8000` (internal Docker network)
- `http://localhost:8000` (from host machine)

## API Endpoints

### MCP Server

- `POST /mcp/init` - Initialize a new FEA job
- `GET /mcp/{job_id}` - Get job state
- `PUT /mcp/{job_id}/status` - Update job status
- `GET /mcp/queue/next` - Get next pending job

See `services/mcp-server/README.md` for detailed API documentation.

## Environment Variables

See `.env.example` for all available environment variables. Key variables:

- `OPENAI_API_KEY` - Required for orchestrator
- `DATABASE_URL` - PostgreSQL connection string
- `ABAQUS_CMD_PATH` - Path to Abaqus executable (for FEA worker)
- `MCP_SERVER_URL` - MCP server URL (default: `http://mcp-server:8000`)

## Testing

### End-to-End Test

1. Start all services: `docker-compose up`
2. Open Streamlit UI: http://localhost:8501
3. Submit a test request: "Create a cantilever beam test with steel material, 1m length, 1000N tip load"
4. Verify job appears in MCP server
5. Verify FEA worker picks up and processes the job

### Service Isolation Testing

Each service can be tested independently:

```bash
# Test MCP Server
curl http://localhost:8000/docs

# Test Orchestrator (requires OpenAI API key)
cd services/orchestrator
python orchestrator.py

# Test FEA Worker (requires MCP server running)
cd services/fea-worker
python fea_worker.py
```

## Troubleshooting

### Services can't communicate

- Ensure all services are on the same Docker network (`fea-network`)
- Check service names match in environment variables
- Verify ports are not conflicting

### Database connection errors

- Ensure PostgreSQL container is healthy: `docker-compose ps`
- Check `DATABASE_URL` format: `postgresql://user:password@host:port/database`
- Verify database credentials match in `.env`

### FEA Worker not processing jobs

- Check `API_BASE_URL` points to MCP server
- Verify jobs exist with status `INITIALIZED`
- Check worker logs: `docker-compose logs fea-worker`

## Contributing

1. Create a feature branch
2. Make changes in the appropriate service directory
3. Update documentation if needed
4. Test locally with Docker Compose
5. Submit a pull request

## License

[Add your license here]

