# graph.py
"""
Graph creation and orchestration logic for the FEA workflow.
"""

from langgraph.graph import StateGraph, END

# Handle imports - try absolute first, fall back to relative
try:
    from orchestrator.state import AgentState
    from orchestrator.nodes import parse_request, validate_physics, submit_job, should_continue_to_submit
except ImportError:
    from .state import AgentState
    from .nodes import parse_request, validate_physics, submit_job, should_continue_to_submit


def create_orchestrator_graph() -> StateGraph:
    """
    Create and configure the orchestrator workflow graph.
    
    Returns:
        Compiled StateGraph ready for execution
    """
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("parse_request", parse_request)
    workflow.add_node("validate_physics", validate_physics)
    workflow.add_node("submit_job", submit_job)
    
    # Define edges
    workflow.set_entry_point("parse_request")
    workflow.add_edge("parse_request", "validate_physics")
    workflow.add_conditional_edges(
        "validate_physics",
        should_continue_to_submit,
        {"submit_job": "submit_job", "END": END}
    )
    workflow.add_edge("submit_job", END)
    
    return workflow.compile()

