# mcp_schema.py

from pydantic import BaseModel, Field
from typing import Literal, Optional
from datetime import datetime

# Define acceptable states for the FEA job (The "Status" field)
FEAJobStatus = Literal[
    "INITIALIZED",
    "INPUT_GENERATED",
    "MESHING_STARTED",
    "RUNNING",
    "COMPLETED",
    "FAILED"
]

# Define acceptable test types, aligning with your 'simulation_runner.py' logic
FEATestType = Literal["CantileverBeam", "TaylorImpact", "TensionTest"]

class Geometry(BaseModel):
    """Defines the dimensions of the structural part."""
    length_m: float = Field(..., gt=0, description="Length in meters.")
    width_m: float = Field(..., gt=0, description="Width in meters.")
    height_m: float = Field(..., gt=0, description="Height in meters.")

class Material(BaseModel):
    """Defines material properties for linear elasticity."""
    name: str
    youngs_modulus_pa: float = Field(..., gt=0, description="Young's Modulus in Pascals (Pa).")
    poisson_ratio: float = Field(..., ge=0.0, le=0.5, description="Poisson's Ratio (0.0 to 0.5).")

class Loading(BaseModel):
    """Defines the applied loads/boundary conditions."""
    tip_load_n: float = Field(..., description="Concentrated force applied at the tip, in Newtons (N).")
    # This section would expand significantly for more complex simulations

class Discretization(BaseModel):
    """Defines the mesh density (number of elements) along each axis."""
    elements_length: int = Field(..., gt=0, description="Elements along the length.")
    elements_width: int = Field(..., gt=0, description="Elements along the width.")
    elements_height: int = Field(..., gt=0, description="Elements along the height.")

class AbaqusInput(BaseModel):
    """
    The main input structure, validated against the LLM's output.
    """
    MODEL_NAME: str = Field(..., description="Unique name for the Abaqus model/job.")
    TEST_TYPE: FEATestType = Field(..., description="The type of simulation workflow to execute.")

    GEOMETRY: Geometry
    MATERIAL: Material
    LOADING: Loading
    DISCRETIZATION: Discretization

class FEAJobContext(BaseModel):
    """
    The central, authoritative state object for the entire FEA job.
    """
    job_id: str = Field(..., description="Unique, server-generated ID for this job.")
    
    # State and Metadata
    current_status: FEAJobStatus = Field("INITIALIZED", description="The current stage of the FEA workflow.")
    job_name: str = Field(..., description="User-provided human-readable job identifier.")
    last_updated: datetime = Field(default_factory=datetime.utcnow, description="Timestamp of the last modification.")
    
    # Data Container
    input_parameters: AbaqusInput
    logs: list[str] = Field(default_factory=list, description="Historical log of agent actions and status updates.")