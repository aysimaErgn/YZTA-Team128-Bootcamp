from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    """Orkestratör grafiği — ajanlar arası paylaşılan merkezi eyalet."""

    elder_id: str
    conversation_id: str
    user_id: str | None
    user_name: str | None
    user_message: str
    intent: str  # companion | health | escalation
    urgency: str  # low | medium | high
    chat_history: list[dict[str, Any]]
    retrieved_memories: list[str]
    structured_context: dict[str, Any]
    agent_response: str
    escalation_needed: bool
    escalation_reason: str | None
    routed_agent: str
    active_agent: str
    memories_stored: list[str]
    health_decision: dict[str, Any]
    health_tool_results: list[str]
    sms_result: dict[str, Any]
    # --- Ajanlar arası paylaşılan veri ---
    shared_health_context: dict[str, Any]
    detected_mood: str
