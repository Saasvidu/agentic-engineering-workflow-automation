"""
export_preview_png.py

Generate an Abaqus-like PNG preview (deformed + Von Mises contours).

Run with:
  wine64 abaqus cae -script export_preview_png.py

Outputs:
  preview.png
"""

from abaqus import session
from abaqusConstants import *
from odbAccess import openOdb
import os
import json
import traceback


def find_latest_odb():
    odbs = [f for f in os.listdir(".") if f.lower().endswith(".odb")]
    if not odbs:
        return None
    odbs.sort(key=lambda f: os.path.getmtime(f), reverse=True)
    return odbs[0]


def main():
    print("=" * 70)
    print("EXPORT PREVIEW PNG")
    print("=" * 70)
    print("[DEBUG] CWD=" + os.getcwd())

    odb_path = find_latest_odb()
    if not odb_path:
        print("[ERROR] No .odb found in CWD")
        return 2

    print("[INFO] Using ODB: " + odb_path)
    odb = openOdb(odb_path)

    try:
        # Pick last step + last frame (simple, reliable)
        step = list(odb.steps.values())[-1]
        frame = step.frames[-1]

        # Create viewport
        vname = "Viewport-Preview"
        if vname in session.viewports:
            vp = session.viewports[vname]
        else:
            vp = session.Viewport(name=vname)

        vp.setValues(displayedObject=odb)

        # Set to the desired step/frame explicitly
        vp.odbDisplay.setFrame(step=step.name, frame=frame.incrementNumber)

        # Stress contours on deformed shape
        vp.odbDisplay.setPrimaryVariable(
            variableLabel="S",
            outputPosition=INTEGRATION_POINT,
            refinement=(INVARIANT, "Mises"),
        )
        vp.odbDisplay.setDeformedVariable(variableLabel="U")
        vp.odbDisplay.display.setValues(plotState=(CONTOURS_ON_DEF,))

        # Make it look consistent
        vp.view.fitView()

        # IMPORTANT: Abaqus expects fileName without extension
        session.printOptions.setValues(vpDecorations=OFF, reduceColors=False)
        session.printToFile(
            fileName="preview",
            format=PNG,
            canvasObjects=(vp,)
        )

        # Abaqus will create preview.png
        if os.path.exists("preview.png"):
            print("[SUCCESS] Wrote preview.png")
            return 0
        else:
            print("[ERROR] printToFile completed but preview.png not found")
            return 1

    finally:
        try:
            odb.close()
        except:
            pass


if __name__ == "__main__":
    rc = 1
    try:
        rc = main()
    except Exception as e:
        print("[ERROR] Exception: " + str(e))
        traceback.print_exc()
        rc = 1
    finally:
        # CRITICAL: ensure CAE exits (prevents hang)
        try:
            session.exit()
        except:
            pass

    raise SystemExit(rc)
