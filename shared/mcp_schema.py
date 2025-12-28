"""
Shared Pydantic schemas for FEA job configuration and state.

This module defines the data structures used across all services for
validating and serializing FEA simulation parameters and job state.
"""

from pydantic import BaseModel, Field
from typing import Literal
from datetime import datetime


# ============================================================================
# Type Definitions
# ============================================================================

FEAJobStatus = Literal[
    "INITIALIZED",
    "INPUT_GENERATED",
    "MESHING_STARTED",
    "RUNNING",
    "COMPLETED",
    "FAILED"
]

FEATestType = Literal["CantileverBeam", "TaylorImpact", "TensionTest"]


# ============================================================================
# Configuration Models
# ============================================================================

class Geometry(BaseModel):
    """Geometry dimensions of the structural part."""
    length_m: float = Field(..., gt=0, description="Length in meters.")
    width_m: float = Field(..., gt=0, description="Width in meters.")
    height_m: float = Field(..., gt=0, description="Height in meters.")


class Material(BaseModel):
    """Material properties for linear elasticity."""
    name: str
    youngs_modulus_pa: float = Field(..., gt=0, description="Young's Modulus in Pascals (Pa).")
    poisson_ratio: float = Field(..., ge=0.0, le=0.5, description="Poisson's Ratio (0.0 to 0.5).")


class Loading(BaseModel):
    """Applied loads and boundary conditions."""
    tip_load_n: float = Field(..., description="Concentrated force applied at the tip, in Newtons (N).")


class Discretization(BaseModel):
    """Mesh density (number of elements) along each axis."""
    elements_length: int = Field(..., gt=0, description="Elements along the length.")
    elements_width: int = Field(..., gt=0, description="Elements along the width.")
    elements_height: int = Field(..., gt=0, description="Elements along the height.")


class AbaqusInput(BaseModel):
    """Main input structure validated against LLM output."""
    MODEL_NAME: str = Field(..., description="Unique name for the Abaqus model/job.")
    TEST_TYPE: FEATestType = Field(..., description="The type of simulation workflow to execute.")
    GEOMETRY: Geometry
    MATERIAL: Material
    LOADING: Loading
    DISCRETIZATION: Discretization


# ============================================================================
# Job State Model
# ============================================================================

class FEAJobContext(BaseModel):
    """
    Central state object for FEA job.
    
    Pure Pydantic model - single source of truth for job structure.
    """
    job_id: str = Field(..., description="Unique, server-generated ID for this job.")
    current_status: FEAJobStatus = Field(default="INITIALIZED", description="Current stage of the FEA workflow.")
    job_name: str = Field(..., description="User-provided human-readable job identifier.")
    last_updated: datetime = Field(default_factory=datetime.utcnow, description="Timestamp of the last modification.")
    input_parameters: AbaqusInput
    logs: list[str] = Field(default_factory=list, description="Historical log of agent actions and status updates.")


