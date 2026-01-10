"""
vtu_to_glb.py

Convert a VTU (VTK UnstructuredGrid) to a GLB for web viewing.
Run in Fea Worker container

Usage:
  python3 vtu_to_glb.py mesh.vtu mesh.glb
"""

import sys
import numpy as np
import meshio
import trimesh


def extract_surface_triangles(points: np.ndarray, cells: list[meshio.CellBlock]):
    """
    Extract an approximate surface triangle set from tetra/hex/wedge/pyramid cells
    by counting faces and keeping faces that appear only once (boundary faces).

    Returns:
      triangles: (M,3) int array of vertex indices
    """
    # Face templates for common solids (indices in the element's local connectivity)
    face_templates = {
        "tetra": [
            (0, 1, 2),
            (0, 1, 3),
            (0, 2, 3),
            (1, 2, 3),
        ],
        "hexahedron": [
            (0, 1, 2, 3),
            (4, 5, 6, 7),
            (0, 1, 5, 4),
            (2, 3, 7, 6),
            (0, 3, 7, 4),
            (1, 2, 6, 5),
        ],
        "wedge": [
            (0, 1, 2),
            (3, 4, 5),
            (0, 1, 4, 3),
            (1, 2, 5, 4),
            (2, 0, 3, 5),
        ],
        "pyramid": [
            (0, 1, 2, 3),
            (0, 1, 4),
            (1, 2, 4),
            (2, 3, 4),
            (3, 0, 4),
        ],
    }

    # Count faces by sorted vertex tuple (orientation-independent)
    face_count = {}
    face_verts = {}  # store original order for triangulation

    def add_face(v_idx):
        key = tuple(sorted(v_idx))
        face_count[key] = face_count.get(key, 0) + 1
        # keep one representative ordering
        if key not in face_verts:
            face_verts[key] = tuple(v_idx)

    for block in cells:
        ctype = block.type
        data = block.data
        if ctype not in face_templates:
            continue
        templates = face_templates[ctype]
        for elem in data:
            for tpl in templates:
                add_face([int(elem[i]) for i in tpl])

    # Boundary faces appear exactly once
    boundary_faces = [face_verts[k] for k, cnt in face_count.items() if cnt == 1]

    # Triangulate quads
    tris = []
    for f in boundary_faces:
        if len(f) == 3:
            tris.append(f)
        elif len(f) == 4:
            a, b, c, d = f
            tris.append((a, b, c))
            tris.append((a, c, d))

    return np.asarray(tris, dtype=np.int64)


def main():
    if len(sys.argv) != 3:
        print("Usage: python vtu_to_glb.py <in.vtu> <out.glb>")
        return 2

    in_vtu = sys.argv[1]
    out_glb = sys.argv[2]

    mesh = meshio.read(in_vtu)
    points = np.asarray(mesh.points, dtype=np.float64)

    triangles = extract_surface_triangles(points, mesh.cells)
    if triangles.size == 0:
        raise RuntimeError("No surface triangles extracted. Unsupported cell types or empty mesh?")

    tri_mesh = trimesh.Trimesh(vertices=points, faces=triangles, process=False)
    tri_mesh.export(out_glb)
    print(f"[SUCCESS] Wrote {out_glb} ({len(points)} verts, {len(triangles)} tris)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
