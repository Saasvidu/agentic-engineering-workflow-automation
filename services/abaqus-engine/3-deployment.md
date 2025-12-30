# Architecture Deployment Log: Agentic FEA Workflow

## 1. Overview

We deployed a hybrid architecture that bridges Azure Container Apps (ACA) and a Heavy FEA Engine (Abaqus on Wine) running on a dedicated Azure VM. The system uses Azure Files as a high-speed shared "hot folder" for real-time job synchronization.

## 2. Service 1: FEA Worker Agent (Azure Container App)

The Worker is a Python-based background agent that polls the MCP server for jobs.

**Deployment:** Deployed via ACR (`abaqusregistry.azurecr.io/fea-worker-agent:v1`).

### Key Fixes

- **Architecture:** Built using `--platform linux/amd64` to ensure compatibility with Azure's Intel/AMD nodes (fixing Apple Silicon mismatches).

- **Probes:** Disabled Startup/Liveness probes and Ingress to allow the worker to run as a pure background polling loop.

- **Storage:** Mounted the Azure File Share (`abaqus-work-share`) to `/app/jobs` using Container App Environment Storage settings.

## 3. Service 2: Abaqus Engine API (Azure VM)

A Flask REST API running inside a Docker container on the VM to act as a bridge to the Abaqus/Wine environment.

- **Abaqus Bridge:** Receives POST `/run` requests, verifies the directory existence, and executes `wine64 abaqus`.

- **Docker Mapping:** Linked the host's cloud-mount to the container's work-dir:

```bash
-v /media/abaqus-work-share:/home/kasm_user/work
```

## 4. The "Data Bridge" (The Hardest Part)

To make the Worker and the VM see each other's files instantly, we configured a high-performance CIFS mount on the VM.

### Mount Configuration

We bypassed Linux metadata caching and mapped permissions to the internal Docker user (`kasm_user` UID 1000).

- **Mount Point:** `/media/abaqus-work-share`

- **Critical Options:**
  - `cache=none`: Disables directory and attribute caching for instant sync.
  - `uid=1000,gid=1000`: Maps file ownership to the Abaqus user inside Docker.
  - `noperm`: Defers permission checks to the server.

### Permanent Mount (/etc/fstab)

```plaintext
//abqartifacts.file.core.windows.net/abaqus-work-share /media/abaqus-work-share cifs nofail,credentials=/etc/smbcredentials/abqartifacts.cred,dir_mode=0777,file_mode=0777,serverino,mfsymlinks,cache=none,noperm,uid=1000,gid=1000 0 0
```

## 5. Future Tasks & Optimization

### 🛠 Task A: Move File System to Blob

**Goal:** Replace SMB (Azure Files) with the Azure Blob Storage SDK for "Job Input" transfers.

**Reason:** Lower costs and better scalability than SMB mounts, though it requires the Abaqus Engine to manually "Download" before running.

### 🧹 Task B: Re-enable Cleanup

**Goal:** Un-comment the `shutil.rmtree(job_dir)` in `fea_worker.py`.

**Status:** Currently disabled for debugging to ensure files are landing correctly. Once yolo6 and yolo7 pass consistently, this should be re-enabled to prevent storage bloat.

### 🌐 Task C: Web Server Migration

**Goal:** Evaluate if the Abaqus Engine can be moved from a VM into a high-performance Azure Container Instance (ACI) or AKS.

**Constraint:** Depends on Wine/Abaqus GPU and license server requirements.

