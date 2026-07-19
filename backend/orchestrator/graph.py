"""LangGraph orkestratör — intent router + ortak hafıza + 3 ajan."""

from __future__ import annotations

import os
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from orchestrator.memory.long_term import memory_backend_name, search_memories
from orchestrator.memory.shared import (
    hydrate_shared_from_supabase,
    merge_shared_prefer_live,
    recall_shared_context,
)
from orchestrator.memory.short_term import load_recent_messages
from orchestrator.memory.structured import build_structured_context
from orchestrator.nodes.companion import companion_node
from orchestrator.nodes.escalation import escalation_node
from orchestrator.nodes.health import health_node
from orchestrator.router import orchestrator_router, resolve_intent
from orchestrator.state import AgentState

_compiled_graph = None


def load_context_node(state: AgentState) -> AgentState:
    """Uzun süreli + yapısal + ajanlar arası paylaşılan sağlık bağlamını yükler."""
    elder_id = state.get("elder_id") or ""
    conversation_id = state.get("conversation_id") or ""
    query = state.get("user_message") or ""

    memories = search_memories(elder_id, query, limit=5) if elder_id or query else []
    structured = build_structured_context(elder_id or None, conversation_id or None)
    shared = hydrate_shared_from_supabase(conversation_id or None, elder_id or None)
    cached = recall_shared_context(conversation_id or None)
    if cached.get("shared_health_context"):
        shared = merge_shared_prefer_live(shared, cached["shared_health_context"])

    mood = (
        cached.get("detected_mood")
        or state.get("detected_mood")
        or shared.get("detected_mood")
        or "Nötr"
    )

    return {
        **state,
        "retrieved_memories": memories,
        "structured_context": structured,
        "shared_health_context": shared,
        "detected_mood": mood,
    }


def route_node(state: AgentState) -> AgentState:
    """Agent Task Routing: niyet analizi → intent / active_agent."""
    shared = state.get("shared_health_context") or {}
    hint_parts = []
    if shared.get("last_pain_level") is not None:
        hint_parts.append(f"son_ağrı={shared['last_pain_level']}")
    if state.get("detected_mood"):
        hint_parts.append(f"ruh_hali={state.get('detected_mood')}")
    shared_hint = ", ".join(hint_parts) if hint_parts else None

    result = resolve_intent(
        state.get("user_message", ""),
        state.get("chat_history"),
        shared_hint=shared_hint,
    )
    next_node = result.get("next_node") or result.get("intent") or "companion"
    return {
        **state,
        "intent": next_node,
        "urgency": result.get("urgency", "low"),
        "escalation_reason": result.get("reason"),
        "active_agent": next_node,
    }


def pick_agent(state: AgentState) -> Literal["companion", "health", "escalation"]:
    """Conditional edge: router kararındaki düğüme dallan."""
    return orchestrator_router(state)


def check_health_escalation(state: AgentState) -> Literal["escalation", "end"]:
    """PR-2: Sağlık düğümünden sonra anomali varsa Eskalasyon'a geç."""
    if state.get("escalation_needed"):
        return "escalation"
    return "end"


def build_graph():
    workflow = StateGraph(AgentState)
    workflow.add_node("load_context", load_context_node)
    workflow.add_node("router", route_node)
    workflow.add_node("companion", companion_node)
    workflow.add_node("health", health_node)
    workflow.add_node("escalation", escalation_node)

    workflow.add_edge(START, "load_context")
    workflow.add_edge("load_context", "router")
    workflow.add_conditional_edges(
        "router",
        pick_agent,
        {
            "companion": "companion",
            "health": "health",
            "escalation": "escalation",
        },
    )
    workflow.add_edge("companion", END)
    workflow.add_conditional_edges(
        "health",
        check_health_escalation,
        {
            "escalation": "escalation",
            "end": END,
        },
    )
    workflow.add_edge("escalation", END)
    return workflow.compile()


def get_graph():
    global _compiled_graph
    # Geliştirme sırasında düğüm değişikliklerinin yüklenmesi için her seferinde derlenebilir;
    # production'da cache tutulur. Reload ile uvicorn zaten process yeniler.
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph


def reset_graph_cache() -> None:
    global _compiled_graph
    _compiled_graph = None


def run_orchestrator(
    message: str,
    conversation_id: str,
    elder_id: str | None = None,
    user_name: str | None = None,
    user_id: str | None = None,
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Tek giriş noktası — chat/voice endpoint'lerinden çağrılır."""
    chat_history = history if history is not None else load_recent_messages(conversation_id)

    initial: AgentState = {
        "elder_id": elder_id or "",
        "conversation_id": conversation_id or "",
        "user_id": user_id,
        "user_name": user_name,
        "user_message": (message or "").strip(),
        "chat_history": chat_history,
        "retrieved_memories": [],
        "structured_context": {},
        "intent": "companion",
        "urgency": "low",
        "agent_response": "",
        "escalation_needed": False,
        "escalation_reason": None,
        "routed_agent": "companion",
        "active_agent": "",
        "memories_stored": [],
        "shared_health_context": {},
        "detected_mood": "Nötr",
    }

    if not initial["user_message"]:
        return {
            "ai_response": f"{user_name or 'Canım'}, seni duyamadım. Tekrar söyler misin?",
            "intent": "companion",
            "routed_agent": "companion",
            "escalation": False,
            "urgency": "low",
            "memory_backend": memory_backend_name(),
        }

    final_state = get_graph().invoke(initial)
    return {
        "ai_response": final_state.get("agent_response") or "Bir sorun oluştu, tekrar dener misin?",
        "intent": final_state.get("intent", "companion"),
        "routed_agent": final_state.get("routed_agent", "companion"),
        "escalation": bool(final_state.get("escalation_needed")),
        "urgency": final_state.get("urgency", "low"),
        "escalation_reason": final_state.get("escalation_reason"),
        "memories_used": final_state.get("retrieved_memories") or [],
        "memories_stored": final_state.get("memories_stored") or [],
        "memory_backend": memory_backend_name(),
        "detected_mood": final_state.get("detected_mood"),
        "shared_health_context": final_state.get("shared_health_context") or {},
    }


def is_orchestrator_enabled() -> bool:
    return os.getenv("ORCHESTRATOR_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
