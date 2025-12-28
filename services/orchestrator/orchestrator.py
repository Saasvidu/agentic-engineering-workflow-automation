# orchestrator.py
"""
Main orchestrator entry point for FEA simulation job submission.
"""

from langchain_core.messages import HumanMessage

# Handle imports - try absolute first, fall back to relative
try:
    from orchestrator.state import AgentState
    from orchestrator.graph import create_orchestrator_graph
except ImportError:
    from .state import AgentState
    from .graph import create_orchestrator_graph


def run_orchestrator(user_input: str) -> AgentState:
    """
    Execute the orchestrator workflow with the given user input.
    
    Args:
        user_input: Natural language description of the FEA simulation request
        
    Returns:
        Final agent state after workflow execution
    """
    print("=" * 80)
    print("🤖 AGENTIC FEA ORCHESTRATOR (OPENAI BACKEND)")
    print("=" * 80)
    print(f"📝 User Input: {user_input}\n")
    
    # Initialize state
    initial_state: AgentState = {
        "messages": [HumanMessage(content=user_input)],
        "raw_input": user_input,
        "structured_config": None,
        "validation_error": None,
        "submission_status": None
    }
    
    # Create and run workflow
    app = create_orchestrator_graph()
    final_state = app.invoke(initial_state)
    return final_state


if __name__ == "__main__":
    print("=" * 80)
    print("FEA SIMULATION ORCHESTRATOR")
    print("=" * 80)
    print("This system only accepts FEA simulation requests.")
    print("Enter your simulation parameters or press Ctrl+C to exit.\n")
    
    while True:
        try:
            user_input = input("🔬 Enter simulation request: ").strip()
            
            if not user_input:
                print("⚠️  Please enter a valid simulation request.\n")
                continue
            
            # Run the orchestrator
            result = run_orchestrator(user_input)
            
            # Print final status
            print("\n" + "=" * 80)
            if result.get("submission_status"):
                print(f"📊 Final Status: {result['submission_status']}")
            if result.get("validation_error"):
                print(f"⚠️  Validation Error: {result['validation_error']}")
            print("=" * 80 + "\n")
            
        except KeyboardInterrupt:
            print("\n\n👋 Exiting orchestrator. Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {str(e)}\n")
