"""
Orchestrator package for FEA simulation job submission.
"""

try:
    from orchestrator.orchestrator import run_orchestrator
except ImportError:
    from .orchestrator import run_orchestrator

__all__ = ["run_orchestrator"]

