from flask import Flask, request, jsonify
import subprocess
import os

app = Flask(__name__)

@app.route('/run', methods=['POST'])
def run_simulation():
    data = request.json
    job_id = data.get('job_id')
    work_dir = f"/home/kasm_user/work/{job_id}"
    
    # Check if directory exists before trying to enter it
    if not os.path.exists(work_dir):
        return jsonify({
            "status": "error", 
            "message": f"Directory not found: {work_dir}"
        }), 404
    
    cmd = "WINEDEBUG=-all LANG=en_US.1252 wine64 abaqus cae -noGUI simulation_runner.py"
    
    try:
        # We use the full path to simulation_runner.py just to be safe
        result = subprocess.run(cmd, shell=True, cwd=work_dir, capture_output=True, text=True)
        
        if result.returncode == 0:
            return jsonify({"status": "success", "output": result.stdout}), 200
        else:
            return jsonify({"status": "error", "stderr": result.stderr}), 500
    except Exception as e:
        return jsonify({"status": "exception", "details": str(e)}), 500


@app.route('/postprocess', methods=['POST'])
def run_postprocessing():
    """
    Execute post-processing visualization export script.
    
    This endpoint runs after simulation completes to export visualization artifacts
    (VTU mesh, PNG preview, GLB mesh) from the ODB file.
    """
    data = request.json
    job_id = data.get('job_id')
    work_dir = f"/home/kasm_user/work/{job_id}"
    
    # Check if directory exists before trying to enter it
    if not os.path.exists(work_dir):
        return jsonify({
            "status": "error",
            "message": f"Directory not found: {work_dir}"
        }), 404
    
    cmd = "WINEDEBUG=-all LANG=en_US.1252 wine64 abaqus cae -noGUI visualizer_export.py"
    
    try:
        result = subprocess.run(cmd, shell=True, cwd=work_dir, capture_output=True, text=True)
        
        if result.returncode == 0:
            return jsonify({"status": "success", "output": result.stdout}), 200
        else:
            return jsonify({"status": "error", "stderr": result.stderr}), 500
    except Exception as e:
        return jsonify({"status": "exception", "details": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)