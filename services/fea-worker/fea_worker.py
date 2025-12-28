# fea_worker.py - FEA Worker Agent for Abaqus Job Execution

import os
import sys
import time
import json
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime
import requests
from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient

# Load environment variables
load_dotenv()

# Configuration
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://mcp-server:8000")
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "5"))
SIMULATION_RUNNER_PATH = Path(__file__).parent / "lib" / "simulation_runner.py"
JOBS_DIR = Path(__file__).parent / "jobs"
ABAQUS_TIMEOUT_SECONDS = 1800  # 30 minutes
ABAQUS_CMD_PATH = os.getenv("ABAQUS_CMD_PATH")
AZURE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
CONTAINER_NAME = os.getenv("AZURE_STORAGE_CONTAINER_NAME", "fea-job-data")

# Ensure jobs directory exists
JOBS_DIR.mkdir(exist_ok=True)

print("=" * 70)
print("FEA WORKER AGENT")
print("=" * 70)
print(f"API Base URL: {MCP_SERVER_URL}")
print(f"Poll Interval: {POLL_INTERVAL_SECONDS}s")
print(f"Jobs Directory: {JOBS_DIR}")
print(f"Simulation Runner: {SIMULATION_RUNNER_PATH}")
print(f"Abaqus Command: {ABAQUS_CMD_PATH}")
print("=" * 70)


# --- API Client Methods ---

def get_next_job() -> Optional[Dict]:
    """
    Poll the MCP server for the next pending job.
    Returns job context dict or None if queue is empty.
    """
    try:
        response = requests.get(
            f"{MCP_SERVER_URL}/mcp/queue/next",
            timeout=10
        )
        
        if response.status_code == 200:
            job_data = response.json()
            if job_data:  # Check if not null
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
    Returns True if successful, False otherwise.
    """
    try:
        response = requests.put(
            f"{MCP_SERVER_URL}/mcp/{job_id}/status",
            params={
                "new_status": new_status,
                "log_message": log_message
            },
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


# --- Job Execution Methods ---

def prepare_job_directory(job_id: str, input_parameters: Dict) -> Path:
    """
    Create job-specific directory and generate config.json.
    Returns the path to the job directory.
    """
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(exist_ok=True)
    
    # Write config.json in the format expected by simulation_runner.py
    config_path = job_dir / "config.json"
    with open(config_path, 'w') as f:
        json.dump(input_parameters, f, indent=2)
    
    # Copy simulation_runner.py to job directory (Abaqus needs it locally)
    shutil.copy(SIMULATION_RUNNER_PATH, job_dir / "simulation_runner.py")
    
    print(f"📁 Job directory prepared: {job_dir}")
    return job_dir


def run_abaqus_simulation(job_dir: Path, job_id: str) -> bool:
    print(f"🚀 Dispatching Abaqus job {job_id} to Engine container...")
    
    # We map the path from the Worker's perspective to the Engine's perspective
    # Worker Path: /app/jobs/JOB_ID
    # Engine Path: /home/kasm_user/work/JOB_ID
    engine_work_dir = f"/home/kasm_user/work/{job_id}"

    # We use /bin/bash -c to allow environment variables to be set before the wine call
    # Note: we escape the quotes carefully
    full_command = f"WINEDEBUG=-all LANG=en_US.1252 wine64 abaqus cae -noGUI simulation_runner.py"
    
    # The Command: We tell the Engine to run wine + abaqus
    # Note: Using -noGUI is key here for stability
    docker_cmd = [
        "docker", "exec", 
        "-w", engine_work_dir, 
        "abaqus_engine", 
        "/bin/bash", "-c", full_command
    ]
    
    try:
        result = subprocess.run(
            docker_cmd,
            capture_output=True,
            text=True,
            timeout=ABAQUS_TIMEOUT_SECONDS
        )
        
        if result.returncode == 0:
            print(f"✅ Engine completed job {job_id}")
            return True
        else:
            print(f"❌ Engine failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Bridge Error: {e}")
        return False

def upload_job_artifacts_to_azure(job_id: str, local_dir: Path, inputs: Dict, is_failed: bool = False) -> str:
    """
    Handles the recursive upload to Azure Blob Storage.
    """
    conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    container = os.getenv("AZURE_STORAGE_CONTAINER_NAME", "fea-job-data")
    
    if not conn_str:
        print("⚠️ No Azure connection string found. Artifacts lost!")
        return "LOCAL_ONLY"

    service_client = BlobServiceClient.from_connection_string(conn_str)
    
    # 1. Recursive Upload of the Data Folder
    print(f"📤 Uploading results to {container}/{job_id}/data/...")
    for file_path in local_dir.rglob("*"):
        if file_path.is_file():
            # Construct blob path: {job_id}/data/{filename}
            blob_path = f"{job_id}/data/{file_path.name}"
            blob_client = service_client.get_blob_client(container=container, blob=blob_path)
            with open(file_path, "rb") as data:
                blob_client.upload_blob(data, overwrite=True)

    # 2. Create the 'Light' Summary File
    physics_metrics = {}
    results_path = local_dir / "results.json"
    
    if results_path.exists():
        try:
            with open(results_path, 'r') as f:
                physics_metrics = json.load(f)
        except Exception as e:
            print(f"⚠️ Could not parse results.json: {e}")

    # 2. Updated Summary File with Physics Details
    summary = {
        "job_id": job_id,
        "completion_time": datetime.now().isoformat(),
        "status": "FAILED" if is_failed else "SUCCESS",
        "physics_results": physics_metrics,  # <--- HERE IS YOUR DATA!
        "input_summary": {
            "test_type": inputs.get("TEST_TYPE"),
            "material": inputs.get("MATERIAL", {}).get("name")
        },
        "artifact_manifest": [f.name for f in local_dir.iterdir() if f.is_file()]
    }
    
    summary_blob = service_client.get_blob_client(container=container, blob=f"{job_id}/summary.json")
    summary_blob.upload_blob(json.dumps(summary, indent=2), overwrite=True)
    
    return f"https://{service_client.account_name}.blob.core.windows.net/{container}/{job_id}"

def process_job(job: Dict) -> None:
    """
    Process a single FEA job: Execute, Archive to Azure, Summarize, and Cleanup.
    """
    job_id = job["job_id"]
    job_name = job["job_name"]
    input_parameters = job["input_parameters"]
    
    print("\n" + "=" * 70)
    print(f"📋 STARTING JOB: {job_name} (ID: {job_id})")
    print("=" * 70)
    
    # 1. Mark status: RUNNING
    if not update_job_status(job_id, "RUNNING", "Worker initiated local FEA execution"):
        print(f"⚠️  Failed to mark job as RUNNING. Skipping job.")
        return
    
    job_dir = None
    try:
        # 2. Prepare local workspace
        job_dir = prepare_job_directory(job_id, input_parameters)
        
        # 3. Execute Abaqus via Engine Container (The Sidecar Bridge)
        success = run_abaqus_simulation(job_dir, job_id)
        
        if success:
            print(f"✅ Simulation successful. Starting Azure Artifact Persistence...")
            
            # 4. Generate AI-Ready Summary and Upload to Azure
            # We wrap this in a sub-try to ensure simulation failure logic works separately
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
            # Even on failure, we might want to upload logs for debugging
            upload_job_artifacts_to_azure(job_id, job_dir, input_parameters, is_failed=True)
            print(f"❌ Job {job_id} marked as FAILED.")
    
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        update_job_status(job_id, "FAILED", f"Worker Exception: {str(e)}")
    
    finally:
        # 5. Critical Cleanup: Ensure the 4GB VM disk doesn't fill up
        if job_dir and job_dir.exists():
            shutil.rmtree(job_dir)
            print(f"🧹 Local cleanup: Deleted {job_dir}")


# --- Main Polling Loop ---

def main():
    """
    Main polling loop that continuously checks for new jobs.
    """
    print("\n🔄 Starting polling loop... (Press Ctrl+C to stop)\n")
    
    try:
        while True:
            # Poll for next job
            job = get_next_job()
            
            if job:
                # Process the job
                process_job(job)
            else:
                # No jobs available, wait before polling again
                print(f"💤 No jobs in queue. Waiting {POLL_INTERVAL_SECONDS}s...", end="\r")
                time.sleep(POLL_INTERVAL_SECONDS)
    
    except KeyboardInterrupt:
        print("\n\n⛔ Worker shutdown requested by user.")
        print("=" * 70)
        sys.exit(0)
    except Exception as e:
        print(f"\n\n❌ Fatal error in worker: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()


