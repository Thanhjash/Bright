"""Bright — the TeacherAgent service.

Decides what to teach next. Owns the model call and nothing else:
state lives in classroom-core, rendering lives in the UI, the avatar
lives in airi-bridge. See docs/archive/phase-1-plan.md §3.
"""

from .act import ActEmitter, act_event, format_act, format_delay, make_act, to_text_stream
from .base import (
    Act,
    AgentEvent,
    Done,
    TeacherAgent,
    TextDelta,
    ToolCall,
    ToolResult,
    TurnUsage,
)
from .direct import DirectAgent, LLMConfig, build_request_body
from .hermes import (
    HermesAgent,
    HermesConfig,
    HermesProtocolError,
    build_hermes_input,
    build_hermes_request,
    iter_sse_events,
    render_hermes_turn,
)
from .prompt import SYSTEM_PROMPT, build_messages, render_turn
from .tools import (
    CHOOSE_NEXT,
    GET_STATE,
    RECALL,
    RECORD_OBSERVATION,
    SAY,
    TOOL_NAMES,
    ToolExecutor,
    build_tools,
)
from .validation import REJECTION_LOG, Rejection, validate_call

__version__ = "0.1.0"

__all__ = [
    "__version__",
    # seam
    "TeacherAgent",
    "AgentEvent",
    "TextDelta",
    "Act",
    "ToolCall",
    "ToolResult",
    "Done",
    "TurnUsage",
    # implementation
    "DirectAgent",
    "LLMConfig",
    "build_request_body",
    "HermesAgent",
    "HermesConfig",
    "HermesProtocolError",
    "build_hermes_input",
    "build_hermes_request",
    "iter_sse_events",
    "render_hermes_turn",
    # tools
    "ToolExecutor",
    "build_tools",
    "TOOL_NAMES",
    "GET_STATE",
    "CHOOSE_NEXT",
    "SAY",
    "RECORD_OBSERVATION",
    "RECALL",
    # prompt
    "SYSTEM_PROMPT",
    "build_messages",
    "render_turn",
    # validation
    "validate_call",
    "Rejection",
    "REJECTION_LOG",
    # act
    "ActEmitter",
    "act_event",
    "format_act",
    "format_delay",
    "make_act",
    "to_text_stream",
]
