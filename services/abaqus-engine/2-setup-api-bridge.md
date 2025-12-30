# Setup API Bridge

## Overview

This document describes the process of setting up a Flask API bridge that receives signals and triggers the Abaqus solver within the container's environment.

## 2. Flask API Implementation

The Flask API receives HTTP requests and triggers the Abaqus solver execution.

```python
# Location: /home/kasm-user/engine_api.py
from flask import Flask, request, jsonify
import subprocess
import os

app = Flask(__name__)

@app.route('/run', methods=['POST'])
def run_simulation():
    data = request.json
    job_id = data.get('job_id')
    # Use kasm-user (hyphen) as per the directory structure found
    work_dir = f"/home/kasm-user/work/{job_id}"

    if not os.path.exists(work_dir):
        return jsonify({"status": "error", "message": f"Path not found: {work_dir}"}), 404

    # Abaqus Execution Command via Wine
    cmd = "WINEDEBUG=-all LANG=en_US.1252 wine64 abaqus cae -noGUI simulation_runner.py"

    try:
        result = subprocess.run(cmd, shell=True, cwd=work_dir, capture_output=True, text=True)
        if result.returncode == 0:
            return jsonify({"status": "success", "output": result.stdout}), 200
        else:
            return jsonify({"status": "error", "stderr": result.stderr}), 500
    except Exception as e:
        return jsonify({"status": "exception", "details": str(e)}), 500

if __name__ == '__main__':
    # Listen on 0.0.0.0 to allow Docker port mapping
    app.run(host='0.0.0.0', port=5000)
```

## 3. The "Surgery" (Step-by-Step)

### Step A: Infrastructure Preparation

We identified the running container as `abq_worker` and verified the internal home directory structure (`/home/kasm-user`).

### Step B: Environment Modification

- **Dependency Injection**: Installed flask using pip3 within the container.
- **Code Injection**: Created `engine_api.py` in the user's home directory.
- **Startup Logic**: Instead of a separate file, we opted for a combined command string in the entrypoint to ensure both the API and the Kasm Desktop start together.

### Step C: The Gold Image Commit

On the Azure VM Host (`fea-worker-04`), we captured the state of the `abq_worker` container and redefined the entrypoint to boot the API in the background.

```bash
docker commit \
--change='ENTRYPOINT ["/bin/bash", "-c", "python3 /home/kasm-user/engine_api.py & /dockerstartup/vnc_startup.sh"]' \
abq_worker \
abaqusregistry.azurecr.io/abaqus_2024_le:v3-final
```

### Step D: Registry Deployment

The finalized image was pushed to the Azure Container Registry (ACR) for deployment across the worker fleet.

```bash
az acr login --name abaqusregistry
docker push abaqusregistry.azurecr.io/abaqus_2024_le:v3-final
```

## 4. System Architecture

The system now utilizes a **Parallel Startup Model**:

- **Layer 1 (Background)**: Flask API starts on port 5000, waiting for JSON payloads.
- **Layer 2 (Foreground)**: Kasm VNC and Wine environment initialize, allowing for manual inspection if needed.

### The Handshake

- **Orchestrator**: Sends a POST to `http://<worker-ip>:5000/run` with a `job_id`.
- **Container**: Subprocess triggers Wine/Abaqus, solves the model, and returns the exit code and logs as a JSON response.
