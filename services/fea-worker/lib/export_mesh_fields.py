"""
export_mesh_fields.py

Abaqus ODB-to-VTK exporter (headless, no CAE/viewport required).

Run this with:
  abaqus python export_mesh_fields.py
  (in Wine container:)
  WINEDEBUG=-all LANG=en_US.1252 wine64 abaqus python export_mesh_fields.py

Outputs (in current working directory):
  - mesh.vtu  : VTK UnstructuredGrid with POINTS, CELLS, PointData(U, vonMises)
"""

from __future__ import print_function

import os
import json
import math
import traceback

from odbAccess import openOdb


# ----------------------------
# Utilities
# ----------------------------

def find_latest_odb_file():
    """Return newest .odb file in CWD, or None."""
    cwd = os.getcwd()
    odbs = [f for f in os.listdir(cwd) if f.lower().endswith(".odb")]
    if not odbs:
        return None
    odbs.sort(key=lambda f: os.path.getmtime(os.path.join(cwd, f)), reverse=True)
    return odbs[0]


def get_model_name_from_config():
    """Best-effort: compute Abaqus job name from config.json (matches simulation_runner.py)."""
    try:
        with open("config.json", "r") as f:
            cfg = json.load(f)
        raw_name = cfg.get("MODEL_NAME", "Not_Found")
        return "Job_" + str(raw_name).replace("-", "_")[:35]
    except Exception:
        return None


def calc_von_mises_from_six(s11, s22, s33, s12, s13, s23):
    """Von Mises from 6 stress components."""
    return math.sqrt(
        0.5 * (
            (s11 - s22) ** 2 +
            (s22 - s33) ** 2 +
            (s33 - s11) ** 2 +
            6.0 * (s12 ** 2 + s23 ** 2 + s13 ** 2)
        )
    )


def safe_get_field(frame, key):
    """Return fieldOutputs[key] or None."""
    try:
        return frame.fieldOutputs[key]
    except Exception:
        return None


def pick_frame_with_max_displacement(step):
    """
    Choose the frame with maximum nodal displacement magnitude in the given step.
    Falls back to last frame if anything goes wrong.
    """
    try:
        max_mag = -1.0
        best = step.frames[-1]
        for fr in step.frames:
            uf = safe_get_field(fr, "U")
            if uf is None:
                continue
            fr_max = -1.0
            for v in uf.values:
                # v.magnitude exists for vector fields in Abaqus
                try:
                    if v.magnitude > fr_max:
                        fr_max = v.magnitude
                except Exception:
                    pass
            if fr_max > max_mag:
                max_mag = fr_max
                best = fr
        return best
    except Exception:
        return step.frames[-1]


# ----------------------------
# VTU Writer
# ----------------------------

# VTK cell type IDs (subset)
VTK_TETRA = 10
VTK_HEXAHEDRON = 12
VTK_WEDGE = 13
VTK_PYRAMID = 14


def map_abaqus_elem_to_vtk_type(elem_type, nconn):
    """
    Map Abaqus element type string / connectivity length to VTK cell type.
    """
    et = (elem_type or "").upper()

    # Prefer explicit common Abaqus names
    if "C3D8" in et or "HEX" in et:
        return VTK_HEXAHEDRON
    if "C3D4" in et or "TET" in et:
        return VTK_TETRA
    if "C3D6" in et or "WEDGE" in et:
        return VTK_WEDGE
    if "C3D5" in et or "PYRAMID" in et:
        return VTK_PYRAMID

    # Fall back to connectivity length
    if nconn == 8:
        return VTK_HEXAHEDRON
    if nconn == 4:
        return VTK_TETRA
    if nconn == 6:
        return VTK_WEDGE
    if nconn == 5:
        return VTK_PYRAMID

    # Default (best guess)
    return VTK_HEXAHEDRON


def export_vtu_from_odb(odb_path, out_path="mesh.vtu", instance_name=None):
    print("[INFO] Opening ODB: %s" % odb_path)

    odb = openOdb(path=odb_path, readOnly=True)

    try:
        # Use last step by default
        steps = list(odb.steps.values())
        if not steps:
            raise RuntimeError("ODB has no steps.")
        step = steps[-1]

        frame = pick_frame_with_max_displacement(step)
        print("[INFO] Using step '%s' frame #%d" % (step.name, frame.incrementNumber))

        # Fields
        u_field = safe_get_field(frame, "U")
        s_field = safe_get_field(frame, "S")

        if u_field is None:
            raise RuntimeError("Field output 'U' not found in chosen frame.")
        if s_field is None:
            print("[WARN] Field output 'S' not found in chosen frame. vonMises will be zero.")

        # Choose instance
        insts = odb.rootAssembly.instances
        if not insts:
            raise RuntimeError("ODB rootAssembly has no instances.")

        if instance_name and instance_name in insts:
            inst = insts[instance_name]
        else:
            # Pick first instance deterministically
            inst = list(insts.values())[0]

        print("[INFO] Using instance: %s" % inst.name)

        # Nodes
        nodes = inst.nodes
        if not nodes:
            raise RuntimeError("Instance has no nodes.")

        # Build label->coords and label ordering
        node_coords = {}
        for n in nodes:
            node_coords[n.label] = n.coordinates

        sorted_node_labels = sorted(node_coords.keys())
        node_label_to_index = {lbl: i for i, lbl in enumerate(sorted_node_labels)}

        # Elements
        elements = inst.elements
        if not elements:
            raise RuntimeError("Instance has no elements.")

        cell_connectivity = []  # flattened indices (VTK)
        cell_offsets = []
        cell_types = []

        offset = 0
        for e in elements:
            # IMPORTANT: in ODB, e.connectivity is a tuple of ints (node labels)
            conn_labels = list(e.connectivity)
            conn_indices = [node_label_to_index[lbl] for lbl in conn_labels]

            cell_connectivity.extend(conn_indices)
            offset += len(conn_indices)
            cell_offsets.append(offset)

            vtk_t = map_abaqus_elem_to_vtk_type(getattr(e, "type", ""), len(conn_indices))
            cell_types.append(vtk_t)

        # PointData: displacement U
        disp_by_node = {}
        for v in u_field.values:
            try:
                disp_by_node[v.nodeLabel] = (v.data[0], v.data[1], v.data[2])
            except Exception:
                # Some values may not be nodal; ignore
                pass

        # PointData: vonMises (average integration-point stresses to nodes)
        vm_sum = {}
        vm_cnt = {}

        if s_field is not None:
            for v in s_field.values:
                try:
                    # v.data usually has 6 components for stress tensor
                    data = v.data
                    s11 = data[0] if len(data) > 0 else 0.0
                    s22 = data[1] if len(data) > 1 else 0.0
                    s33 = data[2] if len(data) > 2 else 0.0
                    s12 = data[3] if len(data) > 3 else 0.0
                    s13 = data[4] if len(data) > 4 else 0.0
                    s23 = data[5] if len(data) > 5 else 0.0
                    vm = calc_von_mises_from_six(s11, s22, s33, s12, s13, s23)

                    # Map element value to that element's nodes
                    el = inst.getElementFromLabel(v.elementLabel)
                    for nlbl in el.connectivity:
                        vm_sum[nlbl] = vm_sum.get(nlbl, 0.0) + vm
                        vm_cnt[nlbl] = vm_cnt.get(nlbl, 0) + 1
                except Exception:
                    # Skip any weird stress values (e.g., section points)
                    pass

        def vm_for_node(nlbl):
            c = vm_cnt.get(nlbl, 0)
            if c <= 0:
                return 0.0
            return vm_sum.get(nlbl, 0.0) / float(c)

        # Write VTU (ASCII for simplicity)
        print("[INFO] Writing VTU: %s" % out_path)

        with open(out_path, "w") as f:
            f.write('<?xml version="1.0"?>\n')
            f.write('<VTKFile type="UnstructuredGrid" version="0.1" byte_order="LittleEndian">\n')
            f.write('  <UnstructuredGrid>\n')
            f.write('    <Piece NumberOfPoints="%d" NumberOfCells="%d">\n' % (len(sorted_node_labels), len(elements)))

            # Points
            f.write('      <Points>\n')
            f.write('        <DataArray type="Float64" NumberOfComponents="3" format="ascii">\n')
            for nlbl in sorted_node_labels:
                x, y, z = node_coords[nlbl]
                f.write('          %.6e %.6e %.6e\n' % (x, y, z))
            f.write('        </DataArray>\n')
            f.write('      </Points>\n')

            # Cells
            f.write('      <Cells>\n')

            f.write('        <DataArray type="Int32" Name="connectivity" format="ascii">\n')
            # Write connectivity grouped per cell for readability
            idx = 0
            for e in elements:
                conn_len = len(e.connectivity)
                conn = cell_connectivity[idx:idx + conn_len]
                idx += conn_len
                f.write('          ' + ' '.join(str(i) for i in conn) + '\n')
            f.write('        </DataArray>\n')

            f.write('        <DataArray type="Int32" Name="offsets" format="ascii">\n')
            for off in cell_offsets:
                f.write('          %d\n' % off)
            f.write('        </DataArray>\n')

            f.write('        <DataArray type="UInt8" Name="types" format="ascii">\n')
            for t in cell_types:
                f.write('          %d\n' % t)
            f.write('        </DataArray>\n')

            f.write('      </Cells>\n')

            # PointData
            f.write('      <PointData>\n')

            # Displacement
            f.write('        <DataArray type="Float64" Name="U" NumberOfComponents="3" format="ascii">\n')
            for nlbl in sorted_node_labels:
                ux, uy, uz = disp_by_node.get(nlbl, (0.0, 0.0, 0.0))
                f.write('          %.6e %.6e %.6e\n' % (ux, uy, uz))
            f.write('        </DataArray>\n')

            # vonMises
            f.write('        <DataArray type="Float64" Name="vonMises" NumberOfComponents="1" format="ascii">\n')
            for nlbl in sorted_node_labels:
                f.write('          %.6e\n' % vm_for_node(nlbl))
            f.write('        </DataArray>\n')

            f.write('      </PointData>\n')

            f.write('    </Piece>\n')
            f.write('  </UnstructuredGrid>\n')
            f.write('</VTKFile>\n')

        print("[SUCCESS] Wrote VTU: %s" % out_path)

    finally:
        try:
            odb.close()
        except Exception:
            pass


def main():
    print("=" * 70)
    print("EXPORT MESH + FIELDS (VTU)")
    print("=" * 70)
    print("[DEBUG] CWD=%s" % os.getcwd())

    odb_path = find_latest_odb_file()

    if odb_path is None:
        model_name = get_model_name_from_config()
        if model_name:
            candidate = model_name + ".odb"
            if os.path.exists(candidate):
                odb_path = candidate

    if odb_path is None or not os.path.exists(odb_path):
        print("[ERROR] No ODB file found in current directory.")
        print("[DEBUG] DIR=%s" % ", ".join(os.listdir(os.getcwd())))
        return 2

    try:
        export_vtu_from_odb(odb_path, out_path="mesh.vtu")
        return 0
    except Exception as e:
        print("[ERROR] Export failed: %s" % str(e))
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
