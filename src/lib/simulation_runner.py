# simulation_runner.py - Tier 3 Abaqus Execution Engine

# -----------------------------------------------------
# --- 1. Import Modules ---
# -----------------------------------------------------
from abaqus import *
from abaqusConstants import *
import json  # Standard Python module for reading JSON

# -----------------------------------------------------
# --- 2. Define Test-Specific Functions ---
# -----------------------------------------------------

def run_cantilever_beam(config):
    """
    Executes a cantilever beam simulation based on
    the provided config dictionary.
    """
    
    # --- 2.1. Extract Parameters from Config ---
    MODEL_NAME = config['MODEL_NAME']
    
    # Geometry
    geom = config['GEOMETRY']
    PART_LENGTH = geom['length_m']
    PART_WIDTH = geom['width_m']
    PART_HEIGHT = geom['height_m']
    
    # Material
    mat = config['MATERIAL']
    MAT_NAME = mat['name']
    YOUNGS_MODULUS = mat['youngs_modulus_pa']
    POISSON_RATIO = mat['poisson_ratio']
    
    # Loading
    load = config['LOADING']
    TIP_LOAD = load['tip_load_n']
    
    # Discretization
    disc = config['DISCRETIZATION']
    N_ELEMENTS_LENGTH = disc['elements_length']
    N_ELEMENTS_WIDTH = disc['elements_width']
    N_ELEMENTS_HEIGHT = disc['elements_height']

    # --- 2.2. Node Limit Calculator ---
    total_nodes = (N_ELEMENTS_LENGTH + 1) * (N_ELEMENTS_WIDTH + 1) * (N_ELEMENTS_HEIGHT + 1)
    total_elements = N_ELEMENTS_LENGTH * N_ELEMENTS_WIDTH * N_ELEMENTS_HEIGHT

    print(f"--- MESH PRE-CHECK ---")
    print(f"Elements: {N_ELEMENTS_LENGTH} (L) x {N_ELEMENTS_WIDTH} (W) x {N_ELEMENTS_HEIGHT} (H) = {total_elements} elements")
    print(f"Nodes: {total_nodes} nodes")

    if total_nodes > 1000:
        print(f"!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print(f"WARNING: Node count ({total_nodes}) exceeds")
        print(f"Abaqus Learning Edition limit (1000 nodes).")
        print(f"The 'generateMesh' command will fail.")
        print(f"!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        # You could also 'return' here to stop execution
    else:
        print(f"Node count ({total_nodes}) is within the 1000-node limit.")
    print(f"------------------------")

    # -----------------------------------------------------
    # --- 3. Create Model & Part ---
    # -----------------------------------------------------
    model = mdb.Model(name=MODEL_NAME)
    sketch = model.ConstrainedSketch(name='beamProfile', sheetSize=1.0)
    sketch.rectangle(point1=(-PART_WIDTH/2, -PART_HEIGHT/2), point2=(PART_WIDTH/2, PART_HEIGHT/2))
    part = model.Part(name='Beam', dimensionality=THREE_D, type=DEFORMABLE_BODY)
    part.BaseSolidExtrude(sketch=sketch, depth=PART_LENGTH)

    # -----------------------------------------------------
    # --- 4. Material and Section ---
    # -----------------------------------------------------
    material = model.Material(name=MAT_NAME)
    material.Elastic(table=((YOUNGS_MODULUS, POISSON_RATIO), ))
    section = model.HomogeneousSolidSection(name='BeamSection', material=MAT_NAME)
    region = (part.cells,)
    part.SectionAssignment(region=region, sectionName='BeamSection')

    # -----------------------------------------------------
    # --- 5. Assembly ---
    # -----------------------------------------------------
    assembly = model.rootAssembly
    instance = assembly.Instance(name='BeamInstance', part=part, dependent=ON)

    # -----------------------------------------------------
    # --- 6. Step, Boundary Conditions (BCs), and Load ---
    # -----------------------------------------------------
    step = model.StaticStep(name='Step-1', previous='Initial')
    
    # Find geometry by coordinates
    fixed_face_geom = instance.faces.findAt(((0.0, 0.0, 0.0),)) 
    load_point_geom = instance.vertices.findAt(((PART_WIDTH/2, PART_HEIGHT/2, PART_LENGTH),))
    
    # Create Sets from geometry
    assembly.Set(faces=fixed_face_geom, name='Set-FixedEnd')
    fixed_region = model.rootAssembly.sets['Set-FixedEnd']
    assembly.Set(vertices=load_point_geom, name='Set-LoadPoint')
    load_region = model.rootAssembly.sets['Set-LoadPoint']
    
    # Apply BCs and Loads to the Sets
    model.EncastreBC(name='Fixed', createStepName='Initial', region=fixed_region)
    model.ConcentratedForce(name='TipLoad', createStepName='Step-1', 
                            region=load_region, cf3= -TIP_LOAD)

    # -----------------------------------------------------
    # --- 7. Mesh and Job Submission ---
    # -----------------------------------------------------
    # 1. Assign mesh controls
    part.setMeshControls(regions=part.cells, elemShape=HEX, technique=STRUCTURED)

    # 2. Find edges and group them
    W, H, L = PART_WIDTH, PART_HEIGHT, PART_LENGTH
    W2, H2, L2 = W/2.0, H/2.0, L/2.0

    edges_len_1 = part.edges.findAt(coordinates=( W2,  H2, L2))
    edges_len_2 = part.edges.findAt(coordinates=(-W2,  H2, L2))
    edges_len_3 = part.edges.findAt(coordinates=(-W2, -H2, L2))
    edges_len_4 = part.edges.findAt(coordinates=( W2, -H2, L2))
    length_edges = (edges_len_1, edges_len_2, edges_len_3, edges_len_4)

    edges_wid_1 = part.edges.findAt(coordinates=( 0,  H2, 0))
    edges_wid_2 = part.edges.findAt(coordinates=( 0, -H2, 0))
    edges_wid_3 = part.edges.findAt(coordinates=( 0,  H2, L))
    edges_wid_4 = part.edges.findAt(coordinates=( 0, -H2, L))
    width_edges = (edges_wid_1, edges_wid_2, edges_wid_3, edges_wid_4)

    edges_hgt_1 = part.edges.findAt(coordinates=( W2, 0, 0))
    edges_hgt_2 = part.edges.findAt(coordinates=(-W2, 0, 0))
    edges_hgt_3 = part.edges.findAt(coordinates=( W2, 0, L))
    edges_hgt_4 = part.edges.findAt(coordinates=(-W2, 0, L))
    height_edges = (edges_hgt_1, edges_hgt_2, edges_hgt_3, edges_hgt_4)

    # 3. Apply seeds by number
    part.seedEdgeByNumber(edges=length_edges, number=N_ELEMENTS_LENGTH, constraint=FIXED)
    part.seedEdgeByNumber(edges=width_edges, number=N_ELEMENTS_WIDTH, constraint=FIXED)
    part.seedEdgeByNumber(edges=height_edges, number=N_ELEMENTS_HEIGHT, constraint=FIXED)

    # 4. Generate the mesh on the part
    part.generateMesh()
    
    # 5. Create and submit the job
    job = mdb.Job(name=MODEL_NAME, model=MODEL_NAME, type=ANALYSIS)
    
    # NOTE: To run in non-GUI mode, uncomment these lines:
    # job.submit(consistencyChecking=OFF)
    # job.waitForCompletion() 

    print(f"Abaqus model '{MODEL_NAME}' created and meshed successfully.")
    print(f"Run the script in Abaqus/CAE using File > Run Script to execute.")


# -----------------------------------------------------
# --- 3. Main Execution (The "Switch") ---
# -----------------------------------------------------
if __name__ == '__main__':
    
    CONFIG_FILE = 'config.json'
    
    # 1. Read JSON (Tier 2)
    print(f"Reading configuration from {CONFIG_FILE}...")
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
    except IOError:
        print(f"Error: {CONFIG_FILE} not found. Make sure it is in the same directory.")
        # In a real script, you'd exit here
        raise
        
    # 2. Logic Switch (Tier 3)
    test_type = config.get('TEST_TYPE')
    
    if test_type == 'CantileverBeam':
        print(f"Executing 'CantileverBeam' workflow...")
        run_cantilever_beam(config)
        
    elif test_type == 'TaylorImpact':
        print(f"Executing 'TaylorImpact' workflow (function not yet implemented)...")
        # run_taylor_impact(config) # <--- You would add this next
        
    else:
        print(f"Error: Unknown TEST_TYPE: '{test_type}' in config.json")

    print("Script execution finished.")