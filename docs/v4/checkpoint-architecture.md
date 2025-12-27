# Project: Agentic Engineering Workflow Automation

## Research Context

Enabling automated FEA (Finite Element Analysis) pipelines for surrogate model training under **Dr. Li**.

---

## 1. System Architecture (Monorepo)

### Infrastructure

- System orchestrated via **Docker Compose**
- Implements a **Sidecar pattern**:
  - A Python **Worker** container controls an **Abaqus Engine** container

### Shared Schema

- Centralized `mcp_schema.py` using **Pydantic**
- Enforces strict, shared data validation across:
  - Orchestrator
  - MCP Server
  - Worker

---

## 2. Component Breakdown

### A. The Orchestrator (LangGraph + GPT-4o-mini)

**Function:**  
Converts natural language engineering requests into structured JSON.

**Logic (3-Node Graph):**

1. **Parse**

   - Extracts engineering parameters:
     - Geometry
     - Material
     - Loading / boundary conditions

2. **Validate**

   - Performs engineering sanity checks, including:
     - Aspect ratio > 10:1
     - Node / element count limits
     - Material completeness

3. **Submit**
   - Handshakes with MCP Server to initialize the job
   - Endpoint: `POST /init`

---

### B. The MCP Server (FastAPI + SQLAlchemy)

**Function:**  
Acts as the system's **Source of Truth** and **State Machine**.

**Responsibilities:**

- Job initialization (`/init`)
- State retrieval and synchronization
- Status updates from Workers
- Persistent job queue for polling agents
- Stores job definitions, execution states, and results

---

### C. The FEA Worker & Bridge

#### The Worker

- Python agent polling MCP Server:
  - `GET /queue/next`
- Prepares local runtime environment
- Generates:
  - `config.json`
  - `runner.py`
- Dispatches execution commands to Abaqus Engine

#### The Bridge

- Uses Docker socket mount:
  - `/var/run/docker.sock`
- Enables Worker container to execute:
  ```bash
  docker exec <abaqus_engine> <solver_command>
  ```
- Provides controlled access to Abaqus runtime

---

### D. The Abaqus Engine (Custom Wine-on-Docker Layer)

#### Technical Achievement

- Custom Docker image running Abaqus 2024 LE
  - Ubuntu base with Wine
  - Kasm/VNC enabled for optional GUI access
  - Stable headless execution configuration
- Simulation Runner
  - Tier-3 Python script executed via:
    - `abaqus cae -noGUI runner.py`

#### Responsibilities

- Geometry creation
- Mesh generation
- Boundary and load application
- Solver execution

#### Key Fixes Implemented

- Filename Sanitization
  - Automatic `J_` prefixing
  - Underscore replacement
  - Ensures compliance with Abaqus naming constraints
- Headless Execution Stability
  - `WINEDEBUG=-all`
  - `LANG=en_US.1252`
  - Eliminates Wine locale and rendering issues
- Data Extraction
  - Direct parsing of `.odb` binary
  - Extracts physics metrics such as:
    - Max displacement (e.g., 2.88 × 10⁻⁵ m)

## 3. Data Flow Path

```
User Input
    ↓
Orchestrator (Natural Language → Structured JSON)
    ↓ POST /init
MCP Server (State Machine + Persistent Queue)
    ↓ GET /queue/next
FEA Worker
    ↓
Shared Volume (config.json + runner.py)
    ↓
Abaqus Engine (docker exec → solver)
    ↓
Shared Volume (.odb + results)
    ↓
FEA Worker
    ↓
MCP Server (Status: COMPLETED + Physics Data)
```
