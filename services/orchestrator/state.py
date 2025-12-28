"""
Agent state definition for the orchestrator workflow.
"""

from typing import TypedDict, Annotated, Optional, Sequence
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from shared.mcp_schema import AbaqusInput


class AgentState(TypedDict):
    """State object passed between orchestrator nodes."""
    messages: Annotated[Sequence[BaseMessage], add_messages]
    raw_input: str
    structured_config: Optional[AbaqusInput]
    validation_error: Optional[str]
    submission_status: Optional[str]

