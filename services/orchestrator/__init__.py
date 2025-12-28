# __init__.py
"""
Orchestrator package for FEA simulation job submission.
"""

try:
    # Try absolute import first (when used as a package)
    from orchestrator.orchestrator import run_orchestrator
except ImportError:
    # Fall back to relative import (when run directly)
    from .orchestrator import run_orchestrator

__all__ = ["run_orchestrator"]

