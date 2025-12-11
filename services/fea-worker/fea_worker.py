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

# Load environment variables
load_dotenv()

# Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://mcp-server:8000")
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "5"))
SIMULATION_RUNNER_PATH = Path(__file__).parent / "lib" / "simulation_runner.py"
JOBS_DIR = Path(__file__).parent / "jobs"
ABAQUS_TIMEOUT_SECONDS = 1800  # 30 minutes
ABAQUS_CMD_PATH = os.getenv("ABAQUS_CMD_PATH")

# Ensure jobs directory exists
JOBS_DIR.mkdir(exist_ok=True)

print("=" * 70)
print("FEA WORKER AGENT")
print("=" * 70)
print(f"API Base URL: {API_BASE_URL}")
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
            f"{API_BASE_URL}/mcp/queue/next",
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
            f"{API_BASE_URL}/mcp/{job_id}/status",
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
    """
    Execute the Abaqus simulation in the job directory.
    Returns True if successful, False if failed.
    """
    print(f"🚀 Starting Abaqus execution for job {job_id}...")
    
    abaqus_cmd = os.environ.get("ABAQUS_CMD_PATH")
    if not abaqus_cmd:
        print("\n--- Abaqus Run FAILED ---")
        print("Error: 'ABAQUS_CMD_PATH' not set in your .env file.")
        print("Please add the full path to your 'abaqus.bat' or 'abaqus.exe' file.")
        return False

    # Use the full, absolute path to the Abaqus command
    command = [abaqus_cmd, "cae", "-script", os.path.basename(SIMULATION_RUNNER_PATH)]

    run_env = os.environ.copy()

    
    # Prepare log files
    stdout_log = job_dir / "abaqus_stdout.log"
    stderr_log = job_dir / "abaqus_stderr.log"
    
    try:
        with open(stdout_log, 'w') as out_f, open(stderr_log, 'w') as err_f:
            result = subprocess.run(
                command, 
                env=run_env, 
                cwd=job_dir, 
                stdout=out_f,
                stderr=err_f,
                text=True,
                timeout=ABAQUS_TIMEOUT_SECONDS
            )
        
        # Check return code
        if result.returncode == 0:
            print(f"✅ Abaqus simulation completed successfully")
            return True
        else:
            print(f"❌ Abaqus simulation failed with return code {result.returncode}")
            print(f"   Check logs: {stderr_log}")
            return False
            
    except subprocess.TimeoutExpired:
        print(f"⏱️  Abaqus simulation timed out after {ABAQUS_TIMEOUT_SECONDS}s")
        return False
    except FileNotFoundError:
        print(f"❌ Abaqus executable not found. Is Abaqus installed and in PATH?")
        return False
    except Exception as e:
        print(f"❌ Unexpected error during Abaqus execution: {e}")
        return False


def process_job(job: Dict) -> None:
    """
    Process a single FEA job from start to finish.
    """
    job_id = job["job_id"]
    job_name = job["job_name"]
    input_parameters = job["input_parameters"]
    
    print("\n" + "=" * 70)
    print(f"📋 Processing Job: {job_name} (ID: {job_id})")
    print("=" * 70)
    
    # Step 1: Mark job as RUNNING
    if not update_job_status(job_id, "RUNNING", "Worker agent acquired job and started processing"):
        print(f"⚠️  Failed to mark job as RUNNING. Skipping job.")
        return
    
    try:
        # Step 2: Prepare job directory and config
        job_dir = prepare_job_directory(job_id, input_parameters)
        
        # Step 3: Execute Abaqus simulation
        success = run_abaqus_simulation(job_dir, job_id)
        
        # Step 4: Report final status
        if success:
            update_job_status(
                job_id,
                "COMPLETED",
                f"Abaqus simulation completed successfully. Output in {job_dir}"
            )
            print(f"✅ Job {job_id} marked as COMPLETED")
        else:
            update_job_status(
                job_id,
                "FAILED",
                f"Abaqus simulation failed. Check logs in {job_dir}"
            )
            print(f"❌ Job {job_id} marked as FAILED")
    
    except Exception as e:
        print(f"❌ Unexpected error processing job: {e}")
        update_job_status(
            job_id,
            "FAILED",
            f"Worker encountered unexpected error: {str(e)}"
        )


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

