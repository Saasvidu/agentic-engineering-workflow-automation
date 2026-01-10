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
    work_dir = f"/home/kasm_user/work/{job_id}"

    if not job_id:
        return jsonify({"status": "error", "message": "job_id missing"}), 400

    if not os.path.exists(work_dir):
        return jsonify({"status": "error", "message": f"Directory not found: {work_dir}"}), 404

    # Keep as-is since it already works for you
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
    work_dir = f"/home/kasm_user/work/{job_id}"

    if not job_id:
        return jsonify({"status": "error", "message": "job_id missing"}), 400

    if not os.path.exists(work_dir):
        return jsonify({"status": "error", "message": f"Directory not found: {work_dir}"}), 404

    # Verify scripts exist (helps catch copy/mount issues immediately)
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

    # Step 2: PNG export (best effort; don't fail whole endpoint if this fails)
    cmd_png = "WINEDEBUG=-all LANG=en_US.1252 wine64 abaqus cae -script export_preview_png.py"
    res_png = run_cmd(cmd_png, work_dir)
    steps.append({"name": "export_png", **res_png})

    png_ok = (res_png["returncode"] == 0)

    # Build a clean response
    artifacts = {
        "mesh_vtu_exists": os.path.exists(os.path.join(work_dir, "mesh.vtu")),
        "preview_png_exists": os.path.exists(os.path.join(work_dir, "preview.png")),
    }

    # Decide status code:
    # - If VTU fails: hard fail (this is your core artifact)
    # - If PNG fails but VTU succeeded: return 200 with a warning
    if not vtu_ok:
        return jsonify({
            "status": "error",
            "message": "VTU export failed",
            "artifacts": artifacts,
            "steps": steps,
        }), 500

    # VTU OK, PNG maybe OK
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
    app.run(host='0.0.0.0', port=5000)