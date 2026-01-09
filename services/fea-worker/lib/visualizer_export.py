"""
Abaqus visualization export script for post-processing.

This script runs inside the Abaqus Python environment after simulation completes.
It exports visualization artifacts: VTU mesh, PNG preview, and GLB mesh.
"""

from abaqus import *
from abaqusConstants import *
from odbAccess import openOdb
import json
import math
import os

# Try to import optional libraries for GLB export
try:
    import trimesh
    TRIMESH_AVAILABLE = True
except ImportError:
    TRIMESH_AVAILABLE = False
    print("[WARN] trimesh not available, GLB export will be skipped")

try:
    import pygltf
    PYGLTF_AVAILABLE = True
except ImportError:
    PYGLTF_AVAILABLE = False


def find_odb_file():
    """
    Find the ODB file in the current directory.
    
    Returns:
        ODB file path or None if not found
    """
    # Look for .odb files in current directory
    current_dir = os.getcwd()
    for file in os.listdir(current_dir):
        if file.endswith('.odb'):
            return file
    return None


def get_model_name_from_config():
    """
    Read config.json to get the model name.
    
    Returns:
        Model name string or None if config not found
    """
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
        raw_name = config.get('MODEL_NAME', 'Not_Found')
        return "Job_" + str(raw_name).replace("-", "_")[:35]
    except Exception as e:
        print(f"[WARN] Could not read config.json: {e}")
        return None


def calculate_von_mises(stress_tensor):
    """
    Calculate von Mises stress from stress tensor components.
    
    Args:
        stress_tensor: Abaqus stress tensor (S11, S22, S33, S12, S13, S23)
        
    Returns:
        von Mises stress value
    """
    s11 = stress_tensor.data[0] if len(stress_tensor.data) > 0 else 0.0
    s22 = stress_tensor.data[1] if len(stress_tensor.data) > 1 else 0.0
    s33 = stress_tensor.data[2] if len(stress_tensor.data) > 2 else 0.0
    s12 = stress_tensor.data[3] if len(stress_tensor.data) > 3 else 0.0
    s13 = stress_tensor.data[4] if len(stress_tensor.data) > 4 else 0.0
    s23 = stress_tensor.data[5] if len(stress_tensor.data) > 5 else 0.0
    
    # von Mises formula: sqrt(0.5 * ((S11-S22)^2 + (S22-S33)^2 + (S33-S11)^2 + 6*(S12^2+S23^2+S31^2)))
    vm = math.sqrt(0.5 * (
        (s11 - s22)**2 + 
        (s22 - s33)**2 + 
        (s33 - s11)**2 + 
        6.0 * (s12**2 + s23**2 + s13**2)
    ))
    return vm


def export_vtu(odb_path, output_path='mesh.vtu'):
    """
    Export mesh and results to VTU (VTK Unstructured Grid) format.
    
    Args:
        odb_path: Path to the ODB file
        output_path: Output VTU file path
    """
    print(f"[INFO] Exporting VTU mesh from {odb_path}...")
    
    odb = openOdb(path=odb_path)
    
    # Get the last step and frame (with maximum displacement)
    last_step = odb.steps.values()[-1]
    last_frame = last_step.frames[-1]
    
    # Get field outputs
    displacement_field = last_frame.fieldOutputs['U']
    stress_field = last_frame.fieldOutputs['S']
    
    # Get assembly instance (assuming single instance for CantileverBeam)
    instance = odb.rootAssembly.instances.values()[0]
    
    # Collect nodes and coordinates
    nodes = instance.nodes
    node_coords = {}
    for node in nodes:
        node_coords[node.label] = node.coordinates
    
    # Collect elements and connectivity
    elements = instance.elements
    element_connectivity = []
    element_types = []
    
    for element in elements:
        # Get node labels for this element
        node_labels = [node.label for node in element.connectivity]
        element_connectivity.append(node_labels)
        # Map Abaqus element type to VTK cell type
        # HEX8 (C3D8) -> VTK_HEXAHEDRON (12)
        element_type = element.type
        if 'C3D8' in element_type or 'HEX' in element_type:
            element_types.append(12)  # VTK_HEXAHEDRON
        elif 'C3D4' in element_type or 'TET' in element_type:
            element_types.append(10)  # VTK_TETRA
        else:
            element_types.append(12)  # Default to hexahedron
    
    # Get displacement values at nodes
    displacement_values = {}
    for value in displacement_field.values:
        node_label = value.nodeLabel
        displacement_values[node_label] = (
            value.data[0] if len(value.data) > 0 else 0.0,
            value.data[1] if len(value.data) > 1 else 0.0,
            value.data[2] if len(value.data) > 2 else 0.0
        )
    
    # Get stress values and calculate von Mises at nodes
    # For point data, we'll average element stresses to nodes
    node_stress_count = {}
    node_von_mises = {}
    
    for value in stress_field.values:
        vm = calculate_von_mises(value)
        # Stress values are at integration points, map to nodes
        # For simplicity, average to element nodes
        element_label = value.elementLabel
        element = instance.getElementFromLabel(element_label)
        for node_label in [n.label for n in element.connectivity]:
            if node_label not in node_von_mises:
                node_von_mises[node_label] = 0.0
                node_stress_count[node_label] = 0
            node_von_mises[node_label] += vm
            node_stress_count[node_label] += 1
    
    # Average von Mises stress at nodes
    for node_label in node_von_mises:
        if node_stress_count[node_label] > 0:
            node_von_mises[node_label] /= node_stress_count[node_label]
    
    # Write VTU file
    num_points = len(nodes)
    num_cells = len(elements)
    
    with open(output_path, 'w') as f:
        f.write('<?xml version="1.0"?>\n')
        f.write('<VTKFile type="UnstructuredGrid" version="0.1" byte_order="LittleEndian">\n')
        f.write('  <UnstructuredGrid>\n')
        f.write(f'    <Piece NumberOfPoints="{num_points}" NumberOfCells="{num_cells}">\n')
        
        # Write points
        f.write('      <Points>\n')
        f.write('        <DataArray type="Float64" NumberOfComponents="3" format="ascii">\n')
        for node_label in sorted(node_coords.keys()):
            coords = node_coords[node_label]
            f.write(f'          {coords[0]:.6e} {coords[1]:.6e} {coords[2]:.6e}\n')
        f.write('        </DataArray>\n')
        f.write('      </Points>\n')
        
        # Create mapping from node label to 0-based index
        sorted_node_labels = sorted(node_coords.keys())
        node_label_to_index = {label: idx for idx, label in enumerate(sorted_node_labels)}
        
        # Write cells
        f.write('      <Cells>\n')
        f.write('        <DataArray type="Int32" Name="connectivity" format="ascii">\n')
        for conn in element_connectivity:
            # Map node labels to 0-based indices
            indices = [str(node_label_to_index[label]) for label in conn]
            f.write('          ' + ' '.join(indices) + '\n')
        f.write('        </DataArray>\n')
        
        f.write('        <DataArray type="Int32" Name="offsets" format="ascii">\n')
        offset = 0
        for conn in element_connectivity:
            offset += len(conn)
            f.write(f'          {offset}\n')
        f.write('        </DataArray>\n')
        
        f.write('        <DataArray type="UInt8" Name="types" format="ascii">\n')
        for cell_type in element_types:
            f.write(f'          {cell_type}\n')
        f.write('        </DataArray>\n')
        f.write('      </Cells>\n')
        
        # Write point data (displacement and von Mises)
        f.write('      <PointData>\n')
        
        # Displacement vector
        f.write('        <DataArray type="Float64" Name="U" NumberOfComponents="3" format="ascii">\n')
        for node_label in sorted(node_coords.keys()):
            u = displacement_values.get(node_label, (0.0, 0.0, 0.0))
            f.write(f'          {u[0]:.6e} {u[1]:.6e} {u[2]:.6e}\n')
        f.write('        </DataArray>\n')
        
        # von Mises stress
        f.write('        <DataArray type="Float64" Name="vonMises" NumberOfComponents="1" format="ascii">\n')
        for node_label in sorted(node_coords.keys()):
            vm = node_von_mises.get(node_label, 0.0)
            f.write(f'          {vm:.6e}\n')
        f.write('        </DataArray>\n')
        
        f.write('      </PointData>\n')
        f.write('    </Piece>\n')
        f.write('  </UnstructuredGrid>\n')
        f.write('</VTKFile>\n')
    
    odb.close()
    print(f"[SUCCESS] VTU export complete: {output_path}")


def export_preview_png(odb_path, output_path='preview.png'):
    """
    Export preview PNG image from Abaqus viewport.
    
    Args:
        odb_path: Path to the ODB file
        output_path: Output PNG file path
    """
    print(f"[INFO] Exporting preview PNG from {odb_path}...")
    
    try:
        # Open ODB (keep it open for viewport display)
        odb = openOdb(path=odb_path)
        
        # Find frame with maximum displacement
        last_step = odb.steps.values()[-1]
        max_disp_frame = None
        max_disp_magnitude = 0.0
        
        for frame in last_step.frames:
            displacement_field = frame.fieldOutputs['U']
            frame_max_disp = 0.0
            for value in displacement_field.values:
                if value.magnitude > frame_max_disp:
                    frame_max_disp = value.magnitude
            if frame_max_disp > max_disp_magnitude:
                max_disp_magnitude = frame_max_disp
                max_disp_frame = frame
        
        # Create viewport and display ODB (ODB must remain open)
        viewport_name = 'Viewport-Visualizer'
        if viewport_name in session.viewports.keys():
            viewport = session.viewports[viewport_name]
        else:
            viewport = session.Viewport(name=viewport_name, 
                                       border=ON, 
                                       titleBar=OFF)
        
        viewport.setValues(displayedObject=odb)
        
        # Set display options
        odb_display = viewport.odbDisplay
        odb_display.setPrimaryVariable(
            variableLabel='S',
            outputPosition=INTEGRATION_POINT,
            refinement=(INVARIANT, 'Mises')
        )
        odb_display.setDeformedVariable(variableLabel='U')
        odb_display.display.setValues(plotState=(DEFORMED, CONTOURS_ON_DEF))
        
        # Set view orientation
        viewport.view.setValues(
            nearPlane=0.1,
            farPlane=100.0,
            width=10.0,
            height=10.0,
            cameraPosition=(5, 5, 5),
            cameraUpVector=(0, 0, 1),
            cameraTarget=(0, 0, 0)
        )
        
        # Print to file
        session.printToFile(
            fileName=output_path,
            format=PNG,
            canvasObjects=(viewport,)
        )
        
        # Close ODB after export
        odb.close()
        
        print(f"[SUCCESS] PNG export complete: {output_path}")
        
    except Exception as e:
        print(f"[WARN] PNG export failed: {e}")
        import traceback
        traceback.print_exc()
        # Ensure ODB is closed even on error
        try:
            if 'odb' in locals() and odb:
                odb.close()
        except:
            pass


def export_glb(odb_path, output_path='mesh.glb'):
    """
    Export mesh to GLB format using trimesh or pygltf.
    
    Args:
        odb_path: Path to the ODB file
        output_path: Output GLB file path
    """
    if not TRIMESH_AVAILABLE:
        print("[WARN] GLB export skipped: trimesh library not available")
        return
    
    print(f"[INFO] Exporting GLB mesh from {odb_path}...")
    
    try:
        odb = openOdb(path=odb_path)
        
        # Get instance
        instance = odb.rootAssembly.instances.values()[0]
        
        # Extract surface mesh (faces)
        # For hexahedral elements, extract outer faces
        nodes = instance.nodes
        node_coords = {}
        for node in nodes:
            node_coords[node.label] = node.coordinates
        
        # Collect surface faces
        faces = []
        face_set = set()
        
        elements = instance.elements
        for element in elements:
            node_labels = [n.label for n in element.connectivity]
            if len(node_labels) == 8:  # HEX8
                # Define 6 faces of hexahedron
                hex_faces = [
                    [node_labels[0], node_labels[1], node_labels[2], node_labels[3]],  # bottom
                    [node_labels[4], node_labels[5], node_labels[6], node_labels[7]],  # top
                    [node_labels[0], node_labels[1], node_labels[5], node_labels[4]],  # front
                    [node_labels[2], node_labels[3], node_labels[7], node_labels[6]],  # back
                    [node_labels[0], node_labels[3], node_labels[7], node_labels[4]],  # left
                    [node_labels[1], node_labels[2], node_labels[6], node_labels[5]],  # right
                ]
                for face_nodes in hex_faces:
                    # Create canonical representation
                    face_tuple = tuple(sorted(face_nodes))
                    if face_tuple not in face_set:
                        face_set.add(face_tuple)
                        faces.append(face_nodes)
        
        # Convert to trimesh format
        # Create node label to index mapping (0-based)
        sorted_node_labels = sorted(node_coords.keys())
        node_label_to_index = {label: idx for idx, label in enumerate(sorted_node_labels)}
        
        vertices = []
        for node_label in sorted_node_labels:
            coords = node_coords[node_label]
            vertices.append([coords[0], coords[1], coords[2]])
        
        # Triangulate quad faces
        triangles = []
        for face in faces:
            if len(face) == 4:
                # Split quad into two triangles
                idx0 = node_label_to_index[face[0]]
                idx1 = node_label_to_index[face[1]]
                idx2 = node_label_to_index[face[2]]
                idx3 = node_label_to_index[face[3]]
                triangles.append([idx0, idx1, idx2])
                triangles.append([idx0, idx2, idx3])
            elif len(face) == 3:
                idx0 = node_label_to_index[face[0]]
                idx1 = node_label_to_index[face[1]]
                idx2 = node_label_to_index[face[2]]
                triangles.append([idx0, idx1, idx2])
        
        # Create trimesh and export
        mesh = trimesh.Trimesh(vertices=vertices, faces=triangles)
        mesh.export(output_path)
        
        odb.close()
        print(f"[SUCCESS] GLB export complete: {output_path}")
        
    except Exception as e:
        print(f"[WARN] GLB export failed: {e}")
        import traceback
        traceback.print_exc()


def main():
    """
    Main execution function.
    """
    print("=" * 70)
    print("VISUALIZER EXPORT")
    print("=" * 70)
    
    # Find ODB file
    odb_path = find_odb_file()
    if not odb_path:
        model_name = get_model_name_from_config()
        if model_name:
            odb_path = model_name + '.odb'
        else:
            print("[ERROR] Could not find ODB file")
            return
    
    if not os.path.exists(odb_path):
        print(f"[ERROR] ODB file not found: {odb_path}")
        return
    
    print(f"[INFO] Processing ODB: {odb_path}")
    
    # Export artifacts
    try:
        export_vtu(odb_path, 'mesh.vtu')
    except Exception as e:
        print(f"[ERROR] VTU export failed: {e}")
        import traceback
        traceback.print_exc()
    
    try:
        export_preview_png(odb_path, 'preview.png')
    except Exception as e:
        print(f"[ERROR] PNG export failed: {e}")
        import traceback
        traceback.print_exc()
    
    try:
        export_glb(odb_path, 'mesh.glb')
    except Exception as e:
        print(f"[ERROR] GLB export failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("=" * 70)
    print("[SUCCESS] Visualizer export complete")
    print("=" * 70)


if __name__ == '__main__':
    main()
