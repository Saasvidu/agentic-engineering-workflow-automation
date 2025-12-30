"""
FEA Worker Agent for Abaqus Job Execution

This worker polls the MCP server for pending FEA jobs, executes them using
the Abaqus engine container, and uploads results to Azure Blob Storage.
"""

import os
import sys
import time
import json
import shutil
import threading
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime
import requests
from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient
from flask import Flask, jsonify

# Ensure unbuffered output for better logging in containers
# Set PYTHONUNBUFFERED=1 in Dockerfile for best results
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)
    except Exception:
        pass  # Fallback to default buffering if reconfigure fails

# Load environment variables
load_dotenv()

# ============================================================================
# Configuration
# ============================================================================

# MCP Server Configuration
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://mcp-server:8000")
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "5"))

# Abaqus Engine Configuration
ABAQUS_ENGINE_URL = os.getenv("ABAQUS_ENGINE_URL", "http://abaqus-engine:5000")
ABAQUS_TIMEOUT_SECONDS = int(os.getenv("ABAQUS_TIMEOUT_SECONDS", "1800"))

# Azure Blob Storage Configuration
AZURE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
AZURE_STORAGE_CONTAINER_NAME = os.getenv("AZURE_STORAGE_CONTAINER_NAME", "fea-job-data")

# Health Check Server Configuration
HEALTH_CHECK_PORT = int(os.getenv("HEALTH_CHECK_PORT", "8080"))

# Local Paths
JOBS_DIR = Path(__file__).parent / "jobs"
SIMULATION_RUNNER_PATH = Path(__file__).parent / "lib" / "simulation_runner.py"

# Initialize Flask app for health checks
app = Flask(__name__)

@app.route("/health", methods=["GET"])
@app.route("/", methods=["GET"])
def health_check():
    """Health check endpoint for Azure Container Apps probes."""
    return jsonify({
        "status": "healthy",
        "service": "fea-worker",
        "jobs_directory": str(JOBS_DIR)
    }), 200

# Ensure jobs directory exists
JOBS_DIR.mkdir(exist_ok=True)

# Print startup configuration
print("=" * 70)
print("FEA WORKER AGENT")
print("=" * 70)
print(f"MCP Server URL: {MCP_SERVER_URL}")
print(f"Poll Interval: {POLL_INTERVAL_SECONDS}s")
print(f"Jobs Directory: {JOBS_DIR}")
print(f"Simulation Runner: {SIMULATION_RUNNER_PATH}")
print(f"Abaqus Engine URL: {ABAQUS_ENGINE_URL}")
print(f"Abaqus Engine Endpoint: {ABAQUS_ENGINE_URL}/run")
print(f"Abaqus Timeout: {ABAQUS_TIMEOUT_SECONDS}s")
print("=" * 70)

# ============================================================================
# API Client Methods
# ============================================================================

def get_next_job() -> Optional[Dict]:
    """
    Poll the MCP server for the next pending job.
    
    Returns:
        Job context dict if available, None if queue is empty.
    """
    try:
        response = requests.get(f"{MCP_SERVER_URL}/mcp/queue/next", timeout=10)
        
        if response.status_code == 200:
            job_data = response.json()
            if job_data:
                return job_data
        elif response.status_code != 404:
            print(f"⚠️  Unexpected response from queue endpoint: {response.status_code}")
        
        return None
    except requests.exceptions.RequestException as e:
        print(f"❌ Error polling queue: {e}")
        return None


def update_job_status(job_id: str, new_status: str, log_message: str) -> bool:
    """
    Update the job status on the MCP server.
    
    Args:
        job_id: Unique job identifier
        new_status: New status to set
        log_message: Log message to record
        
    Returns:
        True if successful, False otherwise.
    """
    try:
        response = requests.put(
            f"{MCP_SERVER_URL}/mcp/{job_id}/status",
            params={"new_status": new_status, "log_message": log_message},
            timeout=10
        )
        
        if response.status_code == 200:
            return True
        else:
            print(f"❌ Failed to update status: {response.status_code} - {response.text}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Error updating status: {e}")
        return False


# ============================================================================
# Job Execution Methods
# ============================================================================

def prepare_job_directory(job_id: str, input_parameters: Dict) -> Path:
    """
    Create job-specific directory and generate config.json.
    
    Args:
        job_id: Unique job identifier
        input_parameters: Job input parameters dictionary
        
    Returns:
        Path to the created job directory.
    """
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(exist_ok=True)
    
    # Write config.json for simulation_runner.py
    config_path = job_dir / "config.json"
    with open(config_path, 'w') as f:
        json.dump(input_parameters, f, indent=2)
    
    # Copy simulation_runner.py to job directory (required by Abaqus)
    shutil.copy(SIMULATION_RUNNER_PATH, job_dir / "simulation_runner.py")
    
    print(f"📁 Job directory prepared: {job_dir}")
    return job_dir


def run_abaqus_simulation(job_dir: Path, job_id: str) -> bool:
    """
    Execute Abaqus simulation via the new REST API bridge.
    """
    print(f"🚀 Dispatching Abaqus job {job_id} via Network Bridge...")
    
    payload = {
        "job_id": job_id
    }
    
    try:
        # Use a long timeout because FEA can take a while
        # Note: Engine API expects POST to /run endpoint
        response = requests.post(
            f"{ABAQUS_ENGINE_URL}/run", 
            json=payload, 
            timeout=ABAQUS_TIMEOUT_SECONDS
        )
        
        if response.status_code == 200:
            print(f"✅ Engine completed job {job_id}")
            return True
        else:
            # Safely parse JSON response, handling empty or invalid JSON
            error_data = {}
            if response.content:
                try:
                    error_data = response.json()
                except ValueError as json_err:
                    # Response has content but isn't valid JSON
                    print(f"⚠️  Response is not JSON: {response.text[:200]}")
                    error_data = {"raw_response": response.text[:200]}
            
            error_msg = error_data.get('stderr') or error_data.get('message') or error_data.get('details') or 'No error details'
            print(f"❌ Engine API Error ({response.status_code}): {error_msg}")
            return False
            
    except requests.exceptions.ConnectionError as e:
        print(f"❌ Bridge Error: Cannot connect to Abaqus engine at {ABAQUS_ENGINE_URL}")
        print(f"   Check that ABAQUS_ENGINE_URL is correct and the service is running")
        return False
    except requests.exceptions.Timeout:
        print(f"❌ Bridge Error: Simulation timed out after {ABAQUS_TIMEOUT_SECONDS}s")
        return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Network Bridge Error: {type(e).__name__}: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error during simulation: {type(e).__name__}: {e}")
        return False

def upload_job_artifacts_to_azure(job_id: str, local_dir: Path, inputs: Dict, is_failed: bool = False) -> str:
    """
    Upload job artifacts and results to Azure Blob Storage.
    
    Args:
        job_id: Unique job identifier
        local_dir: Local directory containing job artifacts
        inputs: Job input parameters
        is_failed: Whether the job failed
        
    Returns:
        Azure blob storage URL or "LOCAL_ONLY" if Azure not configured.
    """
    if not AZURE_CONNECTION_STRING:
        print("⚠️ No Azure connection string found. Artifacts lost!")
        return "LOCAL_ONLY"

    service_client = BlobServiceClient.from_connection_string(AZURE_CONNECTION_STRING)
    
    # Upload all files recursively
    print(f"📤 Uploading results to {AZURE_STORAGE_CONTAINER_NAME}/{job_id}/data/...")
    for file_path in local_dir.rglob("*"):
        if file_path.is_file():
            blob_path = f"{job_id}/data/{file_path.name}"
            blob_client = service_client.get_blob_client(
                container=AZURE_STORAGE_CONTAINER_NAME,
                blob=blob_path
            )
            with open(file_path, "rb") as data:
                blob_client.upload_blob(data, overwrite=True)

    # Load physics results if available
    physics_metrics = {}
    results_path = local_dir / "results.json"
    if results_path.exists():
        try:
            with open(results_path, 'r') as f:
                physics_metrics = json.load(f)
        except Exception as e:
            print(f"⚠️ Could not parse results.json: {e}")

    # Create and upload summary file
    summary = {
        "job_id": job_id,
        "completion_time": datetime.now().isoformat(),
        "status": "FAILED" if is_failed else "SUCCESS",
        "physics_results": physics_metrics,
        "input_summary": {
            "test_type": inputs.get("TEST_TYPE"),
            "material": inputs.get("MATERIAL", {}).get("name")
        },
        "artifact_manifest": [f.name for f in local_dir.iterdir() if f.is_file()]
    }
    
    summary_blob = service_client.get_blob_client(
        container=AZURE_STORAGE_CONTAINER_NAME,
        blob=f"{job_id}/summary.json"
    )
    summary_blob.upload_blob(json.dumps(summary, indent=2), overwrite=True)
    
    return f"https://{service_client.account_name}.blob.core.windows.net/{AZURE_STORAGE_CONTAINER_NAME}/{job_id}"

def process_job(job: Dict) -> None:
    """
    Process a single FEA job: execute simulation, upload artifacts, and cleanup.
    
    Args:
        job: Job dictionary containing job_id, job_name, and input_parameters
    """
    job_id = job["job_id"]
    job_name = job["job_name"]
    input_parameters = job["input_parameters"]
    
    print("\n" + "=" * 70)
    print(f"📋 STARTING JOB: {job_name} (ID: {job_id})")
    print("=" * 70)
    
    # Mark job as RUNNING
    if not update_job_status(job_id, "RUNNING", "Worker initiated local FEA execution"):
        print(f"⚠️  Failed to mark job as RUNNING. Skipping job.")
        return
    
    job_dir = None
    try:
        # Prepare workspace and execute simulation
        job_dir = prepare_job_directory(job_id, input_parameters)
        success = run_abaqus_simulation(job_dir, job_id)
        
        if success:
            print(f"✅ Simulation successful. Starting Azure Artifact Persistence...")
            azure_uri = upload_job_artifacts_to_azure(job_id, job_dir, input_parameters)
            
            update_job_status(
                job_id,
                "COMPLETED",
                f"Simulation success. Artifacts stored at: {azure_uri}"
            )
            print(f"🎊 Job {job_id} fully archived and COMPLETED.")
        else:
            update_job_status(
                job_id,
                "FAILED",
                f"Abaqus solver returned non-zero exit code. Check 'data/' logs in Azure."
            )
            # Upload logs even on failure for debugging
            upload_job_artifacts_to_azure(job_id, job_dir, input_parameters, is_failed=True)
            print(f"❌ Job {job_id} marked as FAILED.")
    
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        update_job_status(job_id, "FAILED", f"Worker Exception: {str(e)}")
    
    # finally:
        # Cleanup local files to prevent disk space issues
        # if job_dir and job_dir.exists():
        #     shutil.rmtree(job_dir)
        #     print(f"🧹 Local cleanup: Deleted {job_dir}")


# ============================================================================
# Main Polling Loop
# ============================================================================

def run_worker_loop():
    """
    Main polling loop that continuously checks for new jobs from MCP server.
    """
    print("\n🔄 Starting polling loop... (Press Ctrl+C to stop)\n", flush=True)
    
    try:
        poll_count = 0
        while True:
            poll_count += 1
            if poll_count % 10 == 0:  # Print status every 10 polls (every 50 seconds)
                print(f"💤 Worker active - Poll #{poll_count} (no jobs in queue)", flush=True)
            
            job = get_next_job()
            
            if job:
                process_job(job)
            else:
                # Only print occasionally to avoid log spam
                if poll_count <= 3:  # Print first few polls for debugging
                    print(f"💤 No jobs in queue. Waiting {POLL_INTERVAL_SECONDS}s...", flush=True)
                time.sleep(POLL_INTERVAL_SECONDS)
    
    except KeyboardInterrupt:
        print("\n\n⛔ Worker shutdown requested by user.", flush=True)
        print("=" * 70, flush=True)
        sys.exit(0)
    except Exception as e:
        print(f"\n\n❌ Fatal error in worker: {e}", flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)


def run_health_server():
    """Run Flask health check server in a separate thread."""
    try:
        print(f"🏥 Starting health check server on port {HEALTH_CHECK_PORT}...")
        app.run(host="0.0.0.0", port=HEALTH_CHECK_PORT, debug=False, use_reloader=False)
    except Exception as e:
        print(f"❌ Health server error: {e}")
        import traceback
        traceback.print_exc()


def main():
    """
    Main entry point: starts health check server and worker loop.
    """
    print("=" * 70, flush=True)
    print("🚀 FEA Worker Starting...", flush=True)
    print("=" * 70, flush=True)
    
    try:
        # Start health check server in a background thread
        print("📡 Initializing health check server thread...", flush=True)
        health_thread = threading.Thread(target=run_health_server, daemon=True)
        health_thread.start()
        
        # Give the health server a moment to start
        print("⏳ Waiting for health server to initialize...", flush=True)
        time.sleep(2)
        print("✅ Health server started successfully", flush=True)
        print("🔄 Starting worker polling loop...", flush=True)
        
        # Run the worker loop in the main thread
        run_worker_loop()
    except Exception as e:
        print(f"❌ Fatal error in main: {e}", flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()


