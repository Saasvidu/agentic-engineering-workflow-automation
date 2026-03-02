# Handover Document: Agentic Engineering Workflow Automation

## Executive Summary

This document provides a comprehensive overview of a research project focused on using agentic artificial intelligence to automate engineering workflows, with particular emphasis on Finite Element Analysis (FEA) simulations. The project represents a significant evolution from initial attempts at AI-assisted script generation to a fully distributed system architecture that demonstrates how AI agents can orchestrate complex engineering software workflows.

### Research Context and Evolution

The research project began with a focused investigation into automating Abaqus FEA simulations through AI agent assistance. The initial approach centered on having an AI agent generate Abaqus Python scripts based on natural language descriptions of engineering problems. However, through iterative development and architectural refinement, the project transformed into a broader exploration of distributed agentic systems for engineering research automation.

The ultimate vision that emerged from this research is the creation of a "Cursor for engineering research" — a system where AI agents can understand high-level engineering intents, decompose them into executable simulation workflows, manage state across distributed components, and execute complex engineering software tools seamlessly. This vision positions the work as a foundational framework for future agentic engineering automation systems.

### Project Scope

The current implementation serves as a proof-of-concept demonstration of a distributed agentic engineering system. While the specific instantiation uses Abaqus as the target engineering tool, the architectural patterns and design principles are intended to be generalizable to other engineering software ecosystems. The system demonstrates how natural language interfaces can be bridged to legacy engineering software through a carefully designed middleware layer.

---

## High-Level Model: Distributed Agentic Engineering System

### Theoretical Framework

The research proposes a four-layer distributed architecture for agentic engineering workflow automation. This model separates concerns across distinct functional layers, each responsible for a specific aspect of the workflow transformation from natural language intent to executed simulation results.

#### Layer 1: Orchestrator

The Orchestrator layer serves as the decision-making component that receives natural language input describing engineering problems and determines which simulations need to be executed. This layer operates at the highest level of abstraction, understanding user intent and decomposing complex engineering requests into discrete simulation tasks. The Orchestrator does not concern itself with the specifics of how simulations are configured or executed; rather, it focuses on the "what" and "why" of simulation requirements.

#### Layer 2: Parser

The Parser layer transforms simulation requirements into structured, machine-readable configurations. Each simulation task identified by the Orchestrator is processed by the Parser, which extracts engineering parameters (geometry, material properties, boundary conditions, discretization parameters) and formats them according to a standardized schema. The Parser ensures that all necessary information for simulation execution is captured and validated before proceeding to execution.

#### Layer 3: API/State Management

The API/State layer provides centralized state management and coordination for all simulation jobs. This layer maintains a persistent record of job status, manages job queues, and serves as the single source of truth for the distributed system. The API layer exposes standardized interfaces that allow other components to initialize jobs, query status, update state, and retrieve results. This separation ensures that state management concerns are decoupled from execution logic, enabling fault tolerance and scalability.

#### Layer 4: Worker

The Worker layer is responsible for the actual execution of simulation jobs. Workers poll the API/State layer for pending jobs, retrieve job configurations, prepare execution environments, invoke the appropriate engineering software tools, and report results back to the state management layer. Workers are designed to be stateless and horizontally scalable, allowing multiple workers to process jobs concurrently.

### Design Principles

Several key design principles underpin this architectural model:

1. **Separation of Concerns**: Each layer has a well-defined responsibility, enabling independent development, testing, and scaling.

2. **Stateful Coordination, Stateless Execution**: The API/State layer maintains persistent state, while workers remain stateless, allowing for fault tolerance and horizontal scaling.

3. **Standardized Interfaces**: Communication between layers occurs through well-defined APIs and data schemas, enabling interoperability and future extensibility.

4. **Fault Tolerance**: The distributed nature of the system allows individual component failures without cascading system-wide failures.

5. **Cloud-Native Architecture**: The design is optimized for containerized, cloud-deployable components that can scale independently.

---

## Current Implementation

### Architecture

The current implementation demonstrates the high-level model through a simplified architecture that combines some layers while maintaining the core separation of concerns. The system consists of six main components:

#### 1. Orchestrator/Parser (Combined)

In the current implementation, the Orchestrator and Parser layers are combined into a single service. This service uses LangGraph (a graph-based state machine framework) and GPT-4o-mini (via Azure OpenAI) to process natural language input and generate structured Abaqus simulation configurations.

The workflow consists of three nodes:
- **Parse Node**: Extracts engineering parameters from natural language using structured LLM output
- **Validate Node**: Performs engineering sanity checks (aspect ratios, material properties, mesh density)
- **Submit Node**: Initializes jobs in the MCP Server via REST API

This combined approach simplifies the initial proof-of-concept while still demonstrating the core concept of natural language to structured configuration transformation.

#### 2. MCP Server (API/State Layer)

The Middleware Control Plane (MCP) Server implements the API/State management layer. Built using FastAPI and PostgreSQL, it provides:

- **Job Initialization**: `POST /mcp/init` creates new job contexts with unique identifiers
- **State Retrieval**: `GET /mcp/{job_id}` retrieves complete job state
- **Status Updates**: `PUT /mcp/{job_id}/status` allows workers to update job status
- **Queue Management**: `GET /mcp/queue/next` provides non-blocking job polling for workers

The MCP Server uses a Pydantic-based schema (`FEAJobContext`) as the single source of truth for job structure, ensuring type safety and validation across all components. This design demonstrates how a centralized state management layer can coordinate distributed agents without tight coupling.

#### 3. FEA Worker

The FEA Worker implements the Worker layer as a background polling agent. It continuously polls the MCP Server for pending jobs, processes them sequentially, and coordinates with the Abaqus Engine for execution. The worker handles:

- Job directory preparation and configuration file generation
- Abaqus Engine API communication
- Post-processing coordination (visualization export)
- Artifact upload to Azure Blob Storage
- Status reporting back to MCP Server

The worker demonstrates the stateless execution pattern, where each job is processed independently without maintaining internal state between jobs.

#### 4. Abaqus Engine

The Abaqus Engine represents the engineering software execution environment. It consists of a containerized Abaqus Learning Edition 2024 installation running on Linux via Wine (a Windows compatibility layer). The engine exposes a Flask REST API that receives execution requests and triggers Abaqus solver runs.

This component demonstrates how legacy engineering software can be integrated into a modern, cloud-native architecture through containerization and API bridging.

#### 5. Artifact Store

The Artifact Store (Azure Blob Storage) provides persistent storage for simulation results, logs, and visualization artifacts. The MCP Server generates time-limited, signed URLs for artifact access, enabling secure distribution of results to frontend applications.

#### 6. Frontend

The Frontend is a seperate component developed to present the capabilities of this system. It is a stateless dashboard which queries the API and artifact store to provide graphical information about the simulations which have been conducted.

### Demonstrating the Model

This proof-of-concept implementation demonstrates the high-level model in several key ways:

1. **Natural Language to Execution**: The complete flow from natural language input to executed simulation demonstrates how the Orchestrator/Parser layer bridges human intent to machine execution.

2. **Distributed State Management**: The MCP Server shows how centralized state management enables coordination between multiple distributed components without direct coupling.

3. **Scalable Execution**: The worker pattern demonstrates how stateless execution components can be scaled horizontally to handle increased load.

4. **Legacy Software Integration**: The Abaqus Engine containerization shows how existing engineering software can be integrated into modern distributed architectures.

5. **End-to-End Workflow**: The complete pipeline from user input through execution to artifact storage and frontend visualization demonstrates a production-ready workflow pattern.

---

## Implementation Details

### Service Architecture and Interactions

The system follows a distributed polling architecture where components communicate via REST APIs. The data flow proceeds as follows:

1. **User Input Processing**: Natural language input enters the Orchestrator/Parser service, which uses LangGraph to orchestrate parsing, validation, and job submission.

2. **Job Initialization**: The Orchestrator submits structured configurations to the MCP Server, which generates unique job identifiers and stores job state in PostgreSQL.

3. **Job Polling**: FEA Workers continuously poll the MCP Server for pending jobs using `GET /mcp/queue/next`.

4. **Execution Coordination**: When a worker retrieves a job, it prepares the execution environment, generates configuration files, and sends execution requests to the Abaqus Engine API.

5. **State Updates**: Throughout execution, workers update job status in the MCP Server, providing visibility into job progress.

6. **Artifact Management**: Upon completion, workers upload simulation artifacts to Azure Blob Storage and update job status to COMPLETED.

7. **Frontend Access**: The frontend application queries the MCP Server for job lists and artifact URLs, which are provided as time-limited signed URLs.

### Containerization Achievement: Windows-Only Abaqus on Linux

A significant technical achievement of this project is the successful containerization of Abaqus Learning Edition 2024, which is natively a Windows-only application, to run on Linux infrastructure. This was accomplished through several innovative techniques:

#### Technical Approach

The containerization leverages Wine (Windows compatibility layer) running inside a Docker container based on Ubuntu. The process involves:

1. **Base Environment**: Using `kasmweb/ubuntu-jammy-desktop` as the base image, which provides Xvfb (virtual framebuffer) required for GUI applications.

2. **Wine Configuration**: Wine is configured to emulate Windows 10, providing the necessary runtime environment for Abaqus.

3. **Installation Process**: Following the mwierszycki protocol, Abaqus is installed directly into the Wine prefix without requiring Windows-specific installer checks.

4. **Headless Execution**: The system is configured for headless operation using environment variables (`WINEDEBUG=-all`, `LANG=en_US.1252`) that suppress Wine debugging output and ensure proper locale handling.

5. **Resource Optimization**: The container is optimized for low-resource environments (2 vCPU, 4GB RAM) through careful shared memory configuration (`--shm-size=1g`) and memory limits.

#### Novel Contributions

This containerization represents a novel contribution because:

- **Cloud-Native Legacy Software**: It demonstrates how legacy Windows-only engineering software can be made cloud-native without virtualization overhead.

- **Resource Efficiency**: The solution runs on standard Linux containers without requiring Windows VMs, reducing infrastructure costs and complexity.

- **Reproducibility**: The containerized approach ensures consistent execution environments across different deployment targets.

- **API Bridging**: The Flask API bridge enables programmatic control of Abaqus without requiring GUI access, enabling automation workflows.

The final container image (~20GB) is stored in Azure Container Registry and can be deployed on standard Linux infrastructure, representing a significant advancement in making legacy engineering software accessible to modern cloud-native workflows.

### Artifact Pipeline: VTU/VTU to GLB Conversion

The system implements a sophisticated artifact pipeline that transforms raw simulation outputs into web-viewable formats suitable for frontend visualization.

#### Post-Processing Workflow

After simulation completion, the system executes a two-phase post-processing workflow:

1. **VTU Export**: The Abaqus Engine runs `export_mesh_fields.py` via `abaqus python` (headless, no CAE required). This script:
   - Reads simulation results from the `.odb` (output database) file
   - Extracts nodal coordinates, element connectivity, displacement vectors, and von Mises stress
   - Generates `mesh.vtu` in VTK Unstructured Grid format

2. **PNG Export**: The Abaqus Engine runs `export_preview_png.py` via `abaqus cae -noGUI -script` (requires CAE viewport). This script:
   - Creates an Abaqus viewport visualization
   - Applies stress contours on deformed shape
   - Exports `preview.png` as a static visualization

3. **GLB Conversion**: The FEA Worker performs local conversion of `mesh.vtu` to `mesh.glb` using a custom Python script (`vtu_to_glb.py`). This conversion:
   - Extracts surface triangles from volumetric mesh elements (tetrahedra, hexahedra, wedges, pyramids)
   - Uses boundary face detection to identify surface geometry
   - Converts to GLB format using trimesh library for web-based 3D visualization

#### Design Rationale

This multi-stage artifact pipeline serves several purposes:

- **Format Optimization**: VTU provides complete field data for analysis, while GLB provides optimized geometry for web visualization
- **Separation of Concerns**: Post-processing is separated from simulation execution, allowing independent optimization
- **Fault Tolerance**: The pipeline is designed to continue even if non-critical steps (like PNG export) fail
- **Web Compatibility**: GLB format enables direct 3D visualization in modern web browsers without specialized viewers

### Frontend Integration

The frontend application (developed independently) provides a user interface for interacting with the system. The frontend:

1. **Job Management**: Displays lists of simulation jobs with status indicators
2. **Artifact Visualization**: Renders 3D mesh visualizations using GLB files and displays preview images
3. **Status Monitoring**: Shows real-time job status updates by polling the MCP Server API
4. **Secure Access**: Uses time-limited signed URLs from the MCP Server to access artifacts stored in Azure Blob Storage

The frontend demonstrates how the distributed backend architecture enables flexible client applications without tight coupling. The MCP Server's artifact URL generation ensures secure, controlled access to simulation results without exposing storage credentials to client applications.

---

## Research Contributions and Novel Outcomes

### Primary Contributions

1. **Middleware Control Plane Architecture**: The MCP Server demonstrates a novel approach to coordinating AI agents with legacy engineering software through a centralized state management layer. This pattern is generalizable beyond FEA to other engineering domains.

2. **Legacy Software Containerization**: The successful containerization of Windows-only Abaqus on Linux represents a significant technical achievement that enables cloud-native deployment of legacy engineering tools without virtualization overhead.

3. **Natural Language to Engineering Workflow**: The Orchestrator/Parser demonstrates how structured LLM outputs can reliably transform natural language engineering descriptions into executable simulation configurations with validation.

4. **Distributed Agent Coordination**: The polling-based worker pattern shows how stateless agents can coordinate through a centralized state layer, enabling scalability and fault tolerance.

5. **End-to-End Automation Pipeline**: The complete pipeline from natural language input through execution to visualization demonstrates a production-ready pattern for agentic engineering automation.

### Technical Innovations

- **API Bridging Pattern**: The Flask API bridge enables programmatic control of GUI-based engineering software without requiring interactive sessions.

- **Multi-Format Artifact Pipeline**: The VTU → GLB conversion pipeline demonstrates how simulation outputs can be optimized for both analysis and visualization use cases.

- **Hybrid Cloud Architecture**: The system demonstrates how compute-intensive engineering software (Abaqus Engine on VM) can be integrated with cloud-native services (Container Apps) through shared storage and API communication.

### Limitations and Future Directions

The current implementation has several limitations that represent opportunities for future research:

1. **Simplified Orchestrator**: The current implementation combines Orchestrator and Parser layers. A full implementation would separate these concerns, enabling more sophisticated multi-simulation orchestration.

2. **Single Engineering Tool**: While the architecture is generalizable, the current implementation focuses on Abaqus. Extending to multiple engineering tools would validate the generalizability of the approach.

3. **Limited Test Types**: Currently supports CantileverBeam workflows; TaylorImpact and TensionTest workflows are planned but not fully implemented.

4. **Resource Constraints**: Abaqus Learning Edition has a 1000-node limit, constraining simulation complexity.

5. **Storage Architecture**: Currently uses Azure Files (SMB) for shared storage; migration to Azure Blob Storage SDK would improve scalability.

### Future Research Directions

1. **Multi-Tool Orchestration**: Extend the system to support multiple engineering tools (ANSYS, COMSOL, etc.) through a unified interface.

2. **Advanced Orchestration**: Implement sophisticated multi-simulation workflows with dependency management and parallel execution.

3. **Surrogate Model Training**: Use the automated pipeline for high-throughput parametric studies to train surrogate models for design optimization.

4. **Interactive Refinement**: Enable iterative refinement loops where agents can analyze results and propose parameter adjustments.

5. **Domain-Specific Extensions**: Adapt the architecture for other engineering domains (CFD, structural analysis, thermal analysis, etc.).

---

## Conclusion

This research project demonstrates how agentic AI systems can automate complex engineering workflows through a carefully designed distributed architecture. The proof-of-concept implementation validates the high-level model while producing novel technical contributions in legacy software containerization and agent coordination patterns.

The system serves as a foundation for future research into "Cursor for engineering research" — a vision where AI agents seamlessly bridge natural language intent to complex engineering software execution, enabling researchers and engineers to focus on problem formulation rather than tool-specific implementation details.

The architectural patterns, design principles, and technical solutions developed in this project provide a roadmap for building similar systems in other engineering domains, contributing to the broader goal of democratizing access to advanced engineering simulation capabilities through AI assistance.

---

## Appendix: Key Technical Specifications

### Technology Stack

- **Orchestrator/Parser**: LangGraph, GPT-4o-mini (Azure OpenAI), Streamlit, Pydantic
- **MCP Server**: FastAPI, SQLAlchemy, PostgreSQL, Pydantic
- **FEA Worker**: Python, Flask (health checks), Azure Blob Storage SDK, Requests
- **Abaqus Engine**: Docker, Wine 64-bit, Abaqus LE 2024, Flask API, Kasm/VNC
- **Artifact Store**: Azure Blob Storage
- **Frontend**: Independent React/TypeScript application (separate repository)

### Deployment Architecture

- **Azure Container Apps**: Orchestrator, MCP Server, FEA Worker
- **Azure VM**: Abaqus Engine container
- **Azure Storage**: Blob Storage (artifacts), Files (shared job directories)
- **Azure Database**: PostgreSQL (job state)

### Data Flow Summary

```
Natural Language Input
    ↓
Orchestrator/Parser (LangGraph + LLM)
    ↓
MCP Server (Job Initialization)
    ↓
FEA Worker (Polling + Execution)
    ↓
Abaqus Engine (Simulation)
    ↓
Post-Processing (VTU + PNG Export)
    ↓
GLB Conversion (VTU → GLB)
    ↓
Azure Blob Storage (Artifact Persistence)
    ↓
Frontend (Visualization)
```

---

**Document Version**: 1.0  
**Last Updated**: Based on repository state as of project completion  
**Project Status**: Proof-of-Concept Implementation Complete  
**Research Context**: Agentic AI for Engineering Workflow Automation
