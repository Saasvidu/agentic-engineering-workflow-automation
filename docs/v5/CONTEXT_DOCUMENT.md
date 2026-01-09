# Agentic Engineering Workflow Automation - Complete System Context

## Executive Summary

This repository contains a **Multi-Agent System (MAS)** for automating Finite Element Analysis (FEA) workflows using Abaqus. The system enables high-throughput parametric simulations for surrogate model training under Dr. Li's research program. The core innovation is the **Middleware Control Plane (MCP)** - a stateful coordination layer that bridges LLM-driven agent reasoning with complex Abaqus simulation execution.

**Research Goal:** Enable automated FEA pipelines for surrogate model training  
**Architecture:** Distributed, containerized, cloud-native system  
**Deployment:** Hybrid (Azure Container Apps + Azure VM)  
**Status:** Production-ready with active development

---

## 1. System Architecture Overview

### 1.1 High-Level Architecture

The system implements a **distributed polling architecture** with three main components:

```
┌─────────────────┐
│   Orchestrator  │  (LangGraph + GPT-4o-mini)
│   (Azure ACA)   │  Converts NLP → Structured JSON
└────────┬────────┘
         │ POST /mcp/init
         ▼
┌─────────────────┐
│   MCP Server    │  (FastAPI + PostgreSQL)
│   (Azure ACA)   │  Central State Machine & Queue
└────────┬────────┘
         │ GET /mcp/queue/next
         ▼
┌─────────────────┐
│   FEA Worker    │  (Python Polling Agent)
│   (Azure ACA)   │  Executes Abaqus Jobs
└────────┬────────┘
         │ POST /run (job_id)
         ▼
┌─────────────────┐
│ Abaqus Engine   │  (Docker + Wine + Abaqus LE 2024)
│   (Azure VM)    │  Solves FEA Simulations
└─────────────────┘
```

### 1.2 Design Principles

1. **Stateful & Deterministic:** LangGraph provides explicit control flow for long-running FEA jobs
2. **Fault-Tolerant:** Distributed architecture with persistent state management
3. **Cloud-Native:** Containerized services deployable on Azure Container Apps
4. **Separation of Concerns:** Logic (Brain) separated from execution (Muscle)

---

## 2. Component Breakdown

### 2.1 The Orchestrator (`services/orchestrator/`)

**Purpose:** Convert natural language engineering requests into structured JSON configurations.

**Technology Stack:**
- LangGraph (graph-based state machine)
- GPT-4o-mini (via Azure OpenAI Service)
- Streamlit (web UI)
- Pydantic (structured output validation)

**Workflow (3-Node Graph):**

1. **Parse Node** (`parse_request`)
   - Extracts engineering parameters from NLP input
   - Uses structured LLM output to generate `AbaqusInput` Pydantic model
   - Parameters extracted:
     - Geometry (length, width, height in meters)
     - Material (name, Young's modulus in Pa, Poisson's ratio)
     - Loading (tip load in Newtons)
     - Discretization (elements per dimension)
     - Test type (CantileverBeam, TaylorImpact, TensionTest)

2. **Validate Node** (`validate_physics`)
   - Performs engineering sanity checks:
     - Aspect ratio validation (must be ≥ 10:1)
     - Material property validation (E ≥ 1 GPa)
     - Mesh density validation (≥ 10 elements per dimension)
     - Loading validation (≥ 1000 N)

3. **Submit Node** (`submit_job`)
   - Handshakes with MCP Server via `POST /mcp/init`
   - Creates new job context with generated `job_id`
   - Returns submission status to user

**Key Files:**
- `orchestrator.py` - Main entry point
- `graph.py` - LangGraph workflow definition
- `nodes.py` - Node implementations
- `state.py` - AgentState TypedDict definition
- `prompts.py` - System prompts for LLM
- `config.py` - Environment configuration and LLM setup
- `streamlit_app.py` - Web UI interface

**Environment Variables:**
- `OPENAI_API_KEY` - Azure OpenAI API key
- `MCP_SERVER_URL` - MCP server endpoint (default: `http://mcp-server:8000`)

---

### 2.2 The MCP Server (`services/mcp-server/`)

**Purpose:** Central state management and job queue for the entire system. Acts as the **Source of Truth**.

**Technology Stack:**
- FastAPI (REST API)
- SQLAlchemy (ORM)
- PostgreSQL (production) / SQLite (development)
- Pydantic (shared schema validation)

**Core Responsibilities:**
1. Job initialization (`POST /mcp/init`)
2. State retrieval (`GET /mcp/{job_id}`)
3. Status updates (`PUT /mcp/{job_id}/status`)
4. Queue management (`GET /mcp/queue/next`)

**Database Schema:**

```python
class FEAJob(Base):
    job_id: str (PK)
    job_name: str
    current_status: str (INITIALIZED | INPUT_GENERATED | MESHING_STARTED | RUNNING | COMPLETED | FAILED)
    last_updated: datetime
    input_parameters: JSONB (stores AbaqusInput)
    logs: JSONB (list of log messages)
```

**API Endpoints:**

- `POST /mcp/init` - Initialize new FEA job
  - Parameters: `job_name`, `initial_input` (AbaqusInput JSON)
  - Returns: `FEAJobContext` with generated `job_id`

- `GET /mcp/{job_id}` - Retrieve job state
  - Returns: Complete `FEAJobContext` for the job

- `PUT /mcp/{job_id}/status` - Update job status
  - Parameters: `new_status`, `log_message`
  - Updates status and appends log entry

- `GET /mcp/queue/next` - Poll for next pending job
  - Returns: First job with status `INITIALIZED`, or `None` if empty
  - **Non-blocking** - designed for polling workers

**Key Files:**
- `mcp_server.py` - FastAPI application and endpoints
- `models.py` - SQLAlchemy database models
- `database.py` - Database connection and session management
- `conversions.py` - Pydantic ↔ SQLAlchemy conversion utilities
- `init_db.py` - Database initialization script

**Environment Variables:**
- `DATABASE_URL` - PostgreSQL connection string

---

### 2.3 The FEA Worker (`services/fea-worker/`)

**Purpose:** Background polling agent that executes Abaqus simulations.

**Technology Stack:**
- Python (polling loop)
- Flask (health check server)
- Azure Blob Storage SDK (artifact persistence)
- Requests (HTTP client)

**Execution Flow:**

1. **Polling Loop** (`run_worker_loop`)
   - Continuously polls `GET /mcp/queue/next` every 5 seconds
   - Processes jobs sequentially (one at a time)

2. **Job Processing** (`process_job`)
   - Marks job as `RUNNING` via `PUT /mcp/{job_id}/status`
   - Creates job directory: `jobs/{job_id}/`
   - Generates `config.json` from `input_parameters`
   - Copies `simulation_runner.py` to job directory
   - Dispatches execution to Abaqus Engine via `POST /run`

3. **Abaqus Execution** (`run_abaqus_simulation`)
   - Sends `POST {ABAQUS_ENGINE_URL}/run` with `{"job_id": "..."}`
   - Waits for completion (timeout: 1800 seconds)
   - Handles errors and timeouts

4. **Artifact Upload** (`upload_job_artifacts_to_azure`)
   - Uploads all job files to Azure Blob Storage
   - Creates `summary.json` with physics results
   - Updates job status to `COMPLETED` or `FAILED`

**Key Files:**
- `fea_worker.py` - Main worker implementation
- `lib/simulation_runner.py` - Abaqus execution script (copied to job dirs)
- `lib/config.json` - Example configuration template

**Environment Variables:**
- `MCP_SERVER_URL` - MCP server endpoint
- `ABAQUS_ENGINE_URL` - Abaqus engine API endpoint (default: `http://abaqus-engine:5000`)
- `POLL_INTERVAL_SECONDS` - Polling interval (default: 5)
- `ABAQUS_TIMEOUT_SECONDS` - Simulation timeout (default: 1800)
- `AZURE_STORAGE_CONNECTION_STRING` - Azure Blob Storage connection
- `AZURE_STORAGE_CONTAINER_NAME` - Blob container name (default: `fea-job-data`)
- `HEALTH_CHECK_PORT` - Health check server port (default: 8080)

**Health Check:**
- Flask server runs on port 8080
- Endpoint: `GET /health` or `GET /`
- Returns: `{"status": "healthy", "service": "fea-worker"}`

---

### 2.4 The Abaqus Engine (`services/abaqus-engine/`)

**Purpose:** Execute Abaqus simulations in a containerized environment.

**Technology Stack:**
- Docker (containerization)
- Wine (Windows compatibility layer)
- Abaqus LE 2024 (FEA solver)
- Flask (REST API bridge)
- Kasm/VNC (optional GUI access)

**Container Architecture:**

- **Base Image:** `kasmweb/ubuntu-jammy-desktop:1.14.0`
- **Windows Layer:** Wine 64-bit (Windows 10 mode)
- **FEA Solver:** Abaqus Learning Edition 2024
- **API Bridge:** Flask API (`engine-api.py`) on port 5000
- **GUI Access:** VNC-over-HTTP on port 6901

**Key Technical Achievements:**

1. **Containerization Process:**
   - Abaqus LE 2024 runs on Linux via Wine
   - Custom Docker image (~20GB) stored in Azure Container Registry
   - Image: `abaqusregistry.azurecr.io/abaqus_2024_le:v3-final`

2. **Headless Execution:**
   - Environment variables: `WINEDEBUG=-all LANG=en_US.1252`
   - Command: `wine64 abaqus cae -noGUI simulation_runner.py`
   - Stable execution without GUI dependencies

3. **Filename Sanitization:**
   - Automatic `Job_` prefixing
   - Underscore replacement for special characters
   - Compliance with Abaqus 38-character naming limit

4. **Resource Constraints:**
   - Minimum: 2 vCPU, 4GB RAM
   - Shared memory: `--shm-size=1g` (required for Wine)
   - Memory limit: `--memory="3.5g"` (leaves headroom)

**API Endpoint:**

- `POST /run` - Execute Abaqus simulation
  - Request body: `{"job_id": "uuid"}`
  - Work directory: `/home/kasm_user/work/{job_id}`
  - Executes: `wine64 abaqus cae -noGUI simulation_runner.py`
  - Returns: `{"status": "success"}` or error details

**Simulation Runner (`simulation_runner.py`):**

- Reads `config.json` from current directory
- Executes workflow based on `TEST_TYPE`:
  - `CantileverBeam` - Full workflow implemented
  - `TaylorImpact` - Not yet implemented
  - `TensionTest` - Not yet implemented
- Extracts results from `.odb` file
- Writes `results.json` with physics metrics

**Key Files:**
- `engine-api.py` - Flask API bridge
- `1-containerization-process.md` - Containerization runbook
- `2-setup-api-bridge.md` - API bridge setup guide
- `3-deployment.md` - Deployment architecture

**Deployment:**
- Runs on Azure VM with Azure Files mount
- Mount point: `/media/abaqus-work-share` → `/home/kasm_user/work`
- CIFS mount with `cache=none` for instant sync

---

### 2.5 Shared Schema (`shared/mcp_schema.py`)

**Purpose:** Single source of truth for data structures across all services.

**Technology:** Pydantic v2

**Core Models:**

1. **AbaqusInput** - Input configuration structure
   ```python
   - MODEL_NAME: str
   - TEST_TYPE: Literal["CantileverBeam", "TaylorImpact", "TensionTest"]
   - GEOMETRY: Geometry (length_m, width_m, height_m)
   - MATERIAL: Material (name, youngs_modulus_pa, poisson_ratio)
   - LOADING: Loading (tip_load_n)
   - DISCRETIZATION: Discretization (elements_length, width, height)
   ```

2. **FEAJobContext** - Complete job state
   ```python
   - job_id: str (UUID)
   - current_status: FEAJobStatus
   - job_name: str
   - last_updated: datetime
   - input_parameters: AbaqusInput
   - logs: list[str]
   ```

3. **FEAJobStatus** - Status enumeration
   ```python
   Literal["INITIALIZED", "INPUT_GENERATED", "MESHING_STARTED", 
            "RUNNING", "COMPLETED", "FAILED"]
   ```

**Validation Rules:**
- All geometry dimensions > 0
- Poisson's ratio: 0.0 ≤ ν ≤ 0.5
- Young's modulus > 0
- Element counts > 0

---

## 3. Data Flow Architecture

### 3.1 Complete Workflow

```
1. User Input (NLP)
   ↓
2. Orchestrator (LangGraph)
   ├─ Parse: NLP → AbaqusInput (Pydantic)
   ├─ Validate: Engineering checks
   └─ Submit: POST /mcp/init
   ↓
3. MCP Server (FastAPI)
   ├─ Generate job_id (UUID)
   ├─ Store in PostgreSQL
   └─ Return FEAJobContext
   ↓
4. FEA Worker (Polling Loop)
   ├─ GET /mcp/queue/next (every 5s)
   ├─ Mark job as RUNNING
   ├─ Create job directory: jobs/{job_id}/
   ├─ Write config.json
   ├─ Copy simulation_runner.py
   └─ POST {ABAQUS_ENGINE_URL}/run
   ↓
5. Abaqus Engine (Docker + Wine)
   ├─ Read config.json
   ├─ Execute: wine64 abaqus cae -noGUI simulation_runner.py
   ├─ Generate: .inp, .odb, .log files
   ├─ Extract results from .odb
   └─ Write results.json
   ↓
6. FEA Worker (Post-Processing)
   ├─ Read results.json
   ├─ Upload artifacts to Azure Blob Storage
   ├─ Create summary.json
   └─ PUT /mcp/{job_id}/status (COMPLETED)
   ↓
7. MCP Server (State Update)
   └─ Update database with final status and logs
```

### 3.2 Shared Storage Architecture

**Local Development:**
- Shared volume: `./shared_data/` → `/app/jobs` (worker) and `/home/kasm_user/work` (engine)
- Files synced via Docker volume mounts

**Azure Deployment:**
- Azure Files (SMB) mounted on VM: `/media/abaqus-work-share`
- Mount options: `cache=none,uid=1000,gid=1000,noperm`
- Container mount: `/media/abaqus-work-share` → `/home/kasm_user/work`
- **Future:** Migrate to Azure Blob Storage SDK for better scalability

---

## 4. Deployment Architecture

### 4.1 Container Orchestration

**Docker Compose Files:**
- `docker-compose.orchestrator.yml` - Orchestrator service
- `docker-compose.mcp-server.yml` - MCP Server service
- `docker-compose.fea-worker.yml` - Worker + Abaqus Engine

**Service Dependencies:**
```
orchestrator → mcp-server
fea-worker → mcp-server
fea-worker → abaqus-engine
```

### 4.2 Azure Deployment

**Hybrid Architecture:**

1. **Azure Container Apps (ACA):**
   - Orchestrator (LangGraph + Streamlit)
   - MCP Server (FastAPI + PostgreSQL)
   - FEA Worker (Python polling agent)
   - **Platform:** `linux/amd64`
   - **Scaling:** Auto-scales to zero (free tier)

2. **Azure VM:**
   - Abaqus Engine (Docker container)
   - Azure Files mount for shared storage
   - **Specs:** 2 vCPU, 4GB RAM, 50GB+ disk
   - **Network:** Ports 5000 (API), 6901 (VNC)

3. **Azure Storage:**
   - Azure Files (SMB) - Shared job directories
   - Azure Blob Storage - Long-term artifact storage
   - PostgreSQL Database - Job state persistence

### 4.3 Container Images

**Custom Images:**
- `abaqusregistry.azurecr.io/abaqus_2024_le:v3-final` - Abaqus engine
- `mcp-server` - Built from `Dockerfile.mcp-server`
- `orchestrator` - Built from `Dockerfile.orchestrator`
- `fea-worker` - Built from `Dockerfile.fea-worker`

**Base Images:**
- `kasmweb/ubuntu-jammy-desktop:1.14.0` - Abaqus engine base
- Python 3.10+ for all Python services

---

## 5. Key Design Decisions

### 5.1 Why LangGraph?

**Rationale:**
- **Deterministic Control:** Explicit state machine for long-running FEA jobs
- **Fault Tolerance:** Conditional routing handles errors gracefully
- **Stateful MCP:** Mutable graph state maps cleanly to MCP schema
- **Transparency:** Full control over agent logic (vs. black-box managed systems)

**Alternatives Considered:**
- AWS Bedrock Agents - Vendor lock-in, less transparent
- AutoGen - Conversational state not deterministic enough
- CrewAI - Limited low-level control

### 5.2 Why Distributed Polling?

**Rationale:**
- **Scalability:** Multiple workers can poll independently
- **Fault Tolerance:** Worker failures don't affect queue
- **Long-Running Jobs:** Non-blocking queue allows concurrent job processing
- **Simplicity:** Stateless workers, state managed centrally

**Alternative:** Event-driven (pub/sub) - More complex, requires message broker

### 5.3 Why Hybrid Architecture (ACA + VM)?

**Rationale:**
- **Cost Efficiency:** ACA free tier for stateless services
- **Legacy Software:** Abaqus requires Wine + Windows compatibility
- **Resource Requirements:** FEA solver needs dedicated resources
- **License Constraints:** Abaqus license server may require VM

**Future:** Evaluate Azure Container Instances (ACI) or AKS for Abaqus engine

### 5.4 Why MCP (Middleware Control Plane)?

**Rationale:**
- **Research Contribution:** Novel integration methodology
- **Separation of Concerns:** Logic (LangGraph) vs. State (MCP)
- **Testability:** MCP can be tested independently
- **Interoperability:** Standard REST API for agent communication

---

## 6. Technical Implementation Details

### 6.1 Abaqus Containerization Challenges

**Problem:** Abaqus LE 2024 is Windows-only software.

**Solution:** Wine compatibility layer + Docker containerization.

**Key Fixes:**
1. **Shared Memory:** `--shm-size=1g` prevents Wine crashes
2. **Locale:** `LANG=en_US.1252` fixes Wine locale issues
3. **Debugging:** `WINEDEBUG=-all` suppresses Wine noise
4. **Filename Sanitization:** `Job_` prefix + underscore replacement
5. **Resource Cleanup:** Remove installers before `docker commit` (prevents 40GB+ images)

**Reference:** Based on mwierszycki protocol (Abaqus LE on Linux via Wine)

### 6.2 State Management

**Pydantic ↔ SQLAlchemy Conversion:**
- `pydantic_to_db()` - Converts `FEAJobContext` → `FEAJob` for storage
- `db_to_pydantic()` - Converts `FEAJob` → `FEAJobContext` for API responses
- JSONB storage for flexible schema evolution

**State Transitions:**
```
INITIALIZED → RUNNING → COMPLETED
                ↓
             FAILED
```

### 6.3 Error Handling

**Orchestrator:**
- Validation errors stop workflow before submission
- LLM parsing errors caught and logged
- Network errors retried with exponential backoff

**FEA Worker:**
- Job failures marked as `FAILED` in database
- Artifacts uploaded even on failure (for debugging)
- Timeout handling (1800s default)

**Abaqus Engine:**
- Exit code checking
- `.odb` file validation
- Results extraction error handling

---

## 7. Current Status & Future Work

### 7.1 Completed Features

- ✅ Orchestrator deployment (LangGraph + Streamlit)
- ✅ MCP Server deployment (FastAPI + PostgreSQL)
- ✅ FEA Worker deployment (polling agent)
- ✅ Abaqus containerization (Wine + Docker)
- ✅ Azure Blob Storage integration
- ✅ CantileverBeam workflow
- ✅ Database persistence (PostgreSQL)
- ✅ Health check endpoints

### 7.2 In Progress

- 🔄 Streamlit UI improvements (split columns, 3D viewer)
- 🔄 LangGraph state initialization
- 🔄 Pydantic validation error feedback loop

### 7.3 Planned Features

- ⏳ TaylorImpact workflow implementation
- ⏳ TensionTest workflow implementation
- ⏳ Azure Blob Storage migration (replace Azure Files)
- ⏳ Worker cleanup re-enablement
- ⏳ Web server migration (VM → ACI/AKS)
- ⏳ Integration test suite
- ⏳ Standardized API tool outputs

### 7.4 Known Issues

1. **File Cleanup Disabled:** `shutil.rmtree()` commented out for debugging
2. **Azure Files Dependency:** SMB mount required for VM deployment
3. **Limited Test Types:** Only CantileverBeam fully implemented
4. **Resource Constraints:** Abaqus LE has 1000-node limit

---

## 8. Research Context

### 8.1 Publication Strategy

**Target Venues:**
- **Engineering:** Automation in Construction, Advanced Engineering Informatics
- **AI/CS:** AAMAS, AAAI (AI Applications Track)
- **General:** Applied Sciences, Electronics (Special Issues)

**Paper Focus:**
- **Type:** Systems/Design Paper (not product demo)
- **Core Novelty:** MCP integration methodology
- **Emphasis:** Generalizable framework for agent-engineering software integration

**Key Contributions:**
1. MCP as middleware for LLM-agent coordination
2. Hybrid cloud architecture for legacy FEA software
3. High-throughput parametric simulation automation
4. Fault-tolerant distributed workflow execution

### 8.2 Performance Metrics

**Target Metrics:**
- Speedup factor vs. manual workflows
- Latency reduction
- Scalability (concurrent jobs)
- Reliability (success rate)

**Current Status:** Metrics collection in progress

---

## 9. Development Workflow

### 9.1 Local Development

**Prerequisites:**
- Docker & Docker Compose
- `uv` package manager
- Python 3.10+

**Setup:**
```bash
# MCP Server
cd services/mcp-server
uv sync
source .venv/bin/activate
uvicorn mcp_server:app --reload

# Orchestrator
cd services/orchestrator
uv sync
source .venv/bin/activate
streamlit run streamlit_app.py

# FEA Worker
cd services/fea-worker
uv sync
source .venv/bin/activate
python fea_worker.py
```

**Docker Compose:**
```bash
docker-compose -f docker-compose.orchestrator.yml up
docker-compose -f docker-compose.mcp-server.yml up
docker-compose -f docker-compose.fea-worker.yml up
```

### 9.2 Environment Variables

**Required for Orchestrator:**
- `OPENAI_API_KEY` - Azure OpenAI API key
- `MCP_SERVER_URL` - MCP server endpoint

**Required for MCP Server:**
- `DATABASE_URL` - PostgreSQL connection string

**Required for FEA Worker:**
- `MCP_SERVER_URL` - MCP server endpoint
- `ABAQUS_ENGINE_URL` - Abaqus engine API endpoint
- `AZURE_STORAGE_CONNECTION_STRING` - Azure Blob Storage connection
- `AZURE_STORAGE_CONTAINER_NAME` - Blob container name

### 9.3 Testing

**Integration Tests:**
- Mock Abaqus runs (to avoid license consumption)
- End-to-end workflow tests
- Database state validation

**Unit Tests:**
- Pydantic schema validation
- API endpoint testing
- Node function testing

---

## 10. File Structure Reference

```
agentic-engineering-workflow-automation/
├── services/
│   ├── orchestrator/          # LangGraph orchestration agent
│   │   ├── orchestrator.py     # Main entry point
│   │   ├── graph.py            # LangGraph workflow
│   │   ├── nodes.py            # Node implementations
│   │   ├── state.py            # AgentState definition
│   │   ├── prompts.py          # LLM prompts
│   │   ├── config.py           # Configuration
│   │   └── streamlit_app.py    # Web UI
│   │
│   ├── mcp-server/             # Central state management
│   │   ├── mcp_server.py      # FastAPI application
│   │   ├── models.py           # SQLAlchemy models
│   │   ├── database.py         # DB connection
│   │   ├── conversions.py      # Pydantic ↔ DB conversion
│   │   └── init_db.py          # DB initialization
│   │
│   ├── fea-worker/             # Abaqus execution agent
│   │   ├── fea_worker.py       # Main worker loop
│   │   └── lib/
│   │       ├── simulation_runner.py  # Abaqus execution script
│   │       └── config.json           # Example config
│   │
│   └── abaqus-engine/          # Abaqus containerization docs
│       ├── engine-api.py       # Flask API bridge
│       ├── 1-containerization-process.md
│       ├── 2-setup-api-bridge.md
│       └── 3-deployment.md
│
├── shared/
│   └── mcp_schema.py           # Shared Pydantic schemas
│
├── docs/                       # Documentation
│   ├── v1/                     # Framework selection docs
│   ├── v2/                     # Week 2 sprint docs
│   ├── v3/                     # Week 3 sprint docs
│   ├── v4/                     # Containerization docs
│   ├── v5/                     # Week 5 todos
│   ├── v6/                     # Week 6 todos
│   └── v7/                     # Week 7 todos
│
├── docker-compose.*.yml        # Service-specific compose files
├── Dockerfile.*                # Service-specific Dockerfiles
└── shared_data/                # Local shared storage
```

---

## 11. Key Technical Constraints

### 11.1 Abaqus Learning Edition Limits

- **Node Limit:** 1000 nodes maximum
- **License:** Single concurrent job
- **Platform:** Windows-only (requires Wine)

### 11.2 Resource Requirements

- **Abaqus Engine:** 2 vCPU, 4GB RAM minimum
- **Shared Memory:** 1GB minimum for Wine
- **Storage:** 50GB+ for container image creation

### 11.3 Network Requirements

- **Ports:**
  - 8000 (MCP Server API)
  - 8501 (Streamlit UI)
  - 5000 (Abaqus Engine API)
  - 6901 (VNC GUI access)
  - 8080 (Worker health check)

### 11.4 Azure Constraints

- **Container Apps:** Free tier available
- **VM:** Pay-per-use (no free tier)
- **Storage:** Azure Files (SMB) or Blob Storage
- **Database:** PostgreSQL (managed or self-hosted)

---

## 12. Troubleshooting Guide

### 12.1 Common Issues

**Issue: Worker cannot connect to MCP Server**
- Check `MCP_SERVER_URL` environment variable
- Verify network connectivity (Docker network or host)
- Check MCP Server logs for errors

**Issue: Abaqus simulation fails**
- Check Wine environment variables (`WINEDEBUG=-all LANG=en_US.1252`)
- Verify shared memory (`--shm-size=1g`)
- Check job directory exists and contains `config.json`
- Review Abaqus `.log` and `.msg` files

**Issue: Database connection fails**
- Verify `DATABASE_URL` format (remove quotes, whitespace)
- Check PostgreSQL is running and accessible
- Verify network connectivity

**Issue: Orchestrator cannot parse input**
- Check `OPENAI_API_KEY` is valid
- Verify LLM model is accessible (Azure OpenAI)
- Review prompt engineering in `prompts.py`

### 12.2 Debugging Commands

```bash
# Check MCP Server status
curl http://localhost:8000/docs

# Check worker health
curl http://localhost:8080/health

# Check Abaqus engine API
curl -X POST http://localhost:5000/run -H "Content-Type: application/json" -d '{"job_id":"test"}'

# View database contents
psql $DATABASE_URL -c "SELECT * FROM fea_jobs;"
```

---

## 13. Glossary

- **MCP:** Middleware Control Plane - Central state management system
- **FEA:** Finite Element Analysis
- **ACA:** Azure Container Apps
- **ACR:** Azure Container Registry
- **SMB:** Server Message Block (file sharing protocol)
- **JSONB:** JSON Binary (PostgreSQL data type)
- **VNC:** Virtual Network Computing (remote desktop)
- **Wine:** Windows compatibility layer for Linux
- **LangGraph:** Graph-based state machine framework
- **Pydantic:** Data validation library using Python type annotations

---

## 14. References

### 14.1 External Resources

- **mwierszycki Protocol:** Abaqus LE on Linux via Wine
  - https://github.com/mwierszycki/abaqus_le_linux_wine/tree/main/2024

- **LangGraph Documentation:**
  - https://langchain-ai.github.io/langgraph/

- **Azure Container Apps:**
  - https://learn.microsoft.com/en-us/azure/container-apps/

### 14.2 Internal Documentation

- `docs/v1/framework-hosting-options.md` - Framework selection rationale
- `docs/v1/mcp-approach.md` - MCP design approach
- `docs/v4/containerization-process.md` - Abaqus containerization guide
- `docs/v4/checkpoint-architecture.md` - System architecture overview

---

**Document Version:** 1.0  
**Last Updated:** Based on repository state as of latest commit  
**Maintained By:** Development Team  
**Purpose:** Context document for domain expert agents

