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

DEFAULT_ENV = {
    "WINEDEBUG": "-all",
    "LANG": "en_US.1252",
}

def run_cmd(cmd: str, cwd: str):
    """
    Run a shell command in cwd, capture stdout/stderr, return a structured dict.
    """
    env = os.environ.copy()
    env.update(DEFAULT_ENV)

    result = subprocess.run(
        cmd,
        shell=True,
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
    )

    return {
        "cmd": cmd,
        "returncode": result.returncode,
        "stdout": (result.stdout or "")[-10000:],  # trim to keep responses reasonable
        "stderr": (result.stderr or "")[-10000:],
    }

@app.route('/run', methods=['POST'])
def run_simulation():
    data = request.json or {}
    job_id = data.get('job_id')
    work_dir = f"/home/kasm-user/work/{job_id}"

    if not job_id:
        return jsonify({"status": "error", "message": "job_id missing"}), 400

    if not os.path.exists(work_dir):
        return jsonify({"status": "error", "message": f"Directory not found: {work_dir}"}), 404

    cmd = "WINEDEBUG=-all LANG=en_US.1252 wine64 abaqus cae -noGUI simulation_runner.py"

    try:
        res = run_cmd(cmd, work_dir)
        if res["returncode"] == 0:
            return jsonify({"status": "success", "output": res["stdout"]}), 200
        return jsonify({"status": "error", "stderr": res["stderr"], "debug": res}), 500
    except Exception as e:
        return jsonify({"status": "exception", "details": str(e)}), 500

@app.route('/postprocess', methods=['POST'])
def run_postprocessing():
    """
    Postprocess in two phases:
      1) export_mesh_fields.py (VTU) via: abaqus python
      2) export_preview_png.py (PNG) via: abaqus cae -noGUI -script

    Returns per-step success + logs.
    """
    data = request.json or {}
    job_id = data.get('job_id')
    work_dir = f"/home/kasm-user/work/{job_id}"

    if not job_id:
        return jsonify({"status": "error", "message": "job_id missing"}), 400

    if not os.path.exists(work_dir):
        return jsonify({"status": "error", "message": f"Directory not found: {work_dir}"}), 404

    # Verify scripts exist
    vtu_script = os.path.join(work_dir, "export_mesh_fields.py")
    png_script = os.path.join(work_dir, "export_preview_png.py")

    missing = []
    if not os.path.exists(vtu_script):
        missing.append("export_mesh_fields.py")
    if not os.path.exists(png_script):
        missing.append("export_preview_png.py")

    if missing:
        return jsonify({
            "status": "error",
            "message": f"Missing scripts in job dir: {', '.join(missing)}",
            "work_dir": work_dir
        }), 500

    steps = []

    # Step 1: VTU export (headless, stable)
    cmd_vtu = "WINEDEBUG=-all LANG=en_US.1252 wine64 abaqus python export_mesh_fields.py"
    res_vtu = run_cmd(cmd_vtu, work_dir)
    steps.append({"name": "export_vtu", **res_vtu})

    vtu_ok = (res_vtu["returncode"] == 0)

    # Step 2: PNG export (best effort)
    cmd_png = "WINEDEBUG=-all LANG=en_US.1252 wine64 abaqus cae -noGUI -script export_preview_png.py"
    res_png = run_cmd(cmd_png, work_dir)
    steps.append({"name": "export_png", **res_png})

    png_ok = (res_png["returncode"] == 0)

    # Build response
    artifacts = {
        "mesh_vtu_exists": os.path.exists(os.path.join(work_dir, "mesh.vtu")),
        "preview_png_exists": os.path.exists(os.path.join(work_dir, "preview.png")),
    }

    # If VTU fails: hard fail (core artifact)
    # If PNG fails but VTU succeeded: return 200 with warning
    if not vtu_ok:
        return jsonify({
            "status": "error",
            "message": "VTU export failed",
            "artifacts": artifacts,
            "steps": steps,
        }), 500

    if not png_ok:
        return jsonify({
            "status": "success_with_warning",
            "message": "VTU export succeeded, PNG export failed",
            "artifacts": artifacts,
            "steps": steps,
        }), 200

    return jsonify({
        "status": "success",
        "message": "VTU + PNG export succeeded",
        "artifacts": artifacts,
        "steps": steps,
    }), 200

if __name__ == '__main__':
    # Listen on 0.0.0.0 to allow Docker port mapping
    app.run(host='0.0.0.0', port=5000)
```

## 2.1 Post-Processing Endpoint

The `/postprocess` endpoint executes visualization export in two phases after simulation completes:

1. **VTU Export**: Runs `export_mesh_fields.py` via `abaqus python` (headless, no CAE required)
   - Generates **mesh.vtu**: VTK Unstructured Grid format with nodal coordinates, element connectivity, displacement vectors, and von Mises stress

2. **PNG Export**: Runs `export_preview_png.py` via `abaqus cae -noGUI -script` (requires CAE viewport)
   - Generates **preview.png**: Abaqus viewport screenshot showing deformed shape with von Mises stress contour

The endpoint returns a structured response with per-step status, logs, and artifact verification. If VTU export fails, the endpoint returns an error. If PNG export fails but VTU succeeds, it returns a success with warning status.

**Note**: GLB conversion (VTU to GLB) is performed separately in the FEA worker container after successful postprocessing, not in the Abaqus engine.

The post-processing step is triggered by the FEA worker after the `/run` endpoint completes successfully.

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
abaqusregistry.azurecr.io/abaqus_2024_le:[version]
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

**Two-Stage Execution Flow:**

1. **Simulation Stage**:

   - **FEA Worker**: Sends a POST to `http://<worker-ip>:5000/run` with a `job_id`.
   - **Container**: Subprocess triggers Wine/Abaqus, executes `simulation_runner.py`, solves the model, and returns the exit code and logs as a JSON response.

2. **Post-Processing Stage** (after simulation succeeds):
   - **FEA Worker**: Sends a POST to `http://<worker-ip>:5000/postprocess` with a `job_id`.
   - **Container**: Executes two-phase postprocessing:
     - Phase 1: Runs `export_mesh_fields.py` via `abaqus python` to generate mesh.vtu
     - Phase 2: Runs `export_preview_png.py` via `abaqus cae -noGUI -script` to generate preview.png
     - Returns structured JSON response with per-step status, logs, and artifact verification
   - **FEA Worker**: After successful postprocessing, converts mesh.vtu to mesh.glb locally using `vtu_to_glb.py` script
