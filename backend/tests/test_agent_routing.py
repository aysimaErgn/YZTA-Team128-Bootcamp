"""Agent Task Routing — niyet → companion | health | escalation."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from orchestrator.graph import pick_agent, reset_graph_cache, route_node
from orchestrator.router import (
    RouterDecision,
    orchestrator_router,
    resolve_intent,
    rule_based_intent,
)


def test_rule_health_routing():
    assert rule_based_intent("Sabah ilacımı içtim, sisteme kaydeder misin?") == "health"
    result = resolve_intent("İlacımı aldım")
    assert result["next_node"] == "health"
    assert result["intent"] == "health"


def test_rule_escalation_routing():
    assert rule_based_intent("Banyoda ayağım kaydı ve düştüm, kalkamıyorum!") == "escalation"
    assert rule_based_intent("Başım çok dönüyor, düşmek üzereyim") == "escalation"
    result = resolve_intent("Düştüm kalkamıyorum")
    assert result["next_node"] == "escalation"
    assert result["urgency"] == "high"


def test_rule_companion_leaves_to_llm_or_default():
    assert rule_based_intent("Bana eski günleri anlatır mısın?") is None


def test_router_decision_pydantic_accepts_intent_alias():
    d = RouterDecision.model_validate(
        {"next_node": "companion", "urgency": "low", "reason": "sohbet"}
    )
    assert d.intent == "companion"


def test_route_node_sets_active_agent():
    with patch(
        "orchestrator.graph.resolve_intent",
        return_value={
            "intent": "health",
            "next_node": "health",
            "urgency": "medium",
            "reason": "test",
        },
    ):
        out = route_node(
            {
                "user_message": "İlacımı içtim",
                "chat_history": [],
                "shared_health_context": {},
                "detected_mood": "Nötr",
            }
        )
    assert out["intent"] == "health"
    assert out["active_agent"] == "health"
    assert pick_agent(out) == "health"


def test_orchestrator_router_reads_intent():
    assert orchestrator_router({"intent": "escalation"}) == "escalation"
    assert orchestrator_router({"intent": "companion"}) == "companion"


def test_graph_routes_health_without_llm():
    """Mock resolve_intent → health düğümü active_agent olarak kalır (eskalasyon yok)."""
    from orchestrator.graph import run_orchestrator

    reset_graph_cache()
    health_out = {
        "agent_response": "Kaydettim.",
        "routed_agent": "health",
        "active_agent": "health",
        "escalation_needed": False,
        "memories_stored": [],
        "shared_health_context": {"last_pain_level": None},
        "detected_mood": "Nötr",
    }
    with (
        patch(
            "orchestrator.graph.resolve_intent",
            return_value={
                "intent": "health",
                "next_node": "health",
                "urgency": "medium",
                "reason": "test",
            },
        ),
        patch("orchestrator.graph.search_memories", return_value=[]),
        patch("orchestrator.graph.build_structured_context", return_value={}),
        patch(
            "orchestrator.graph.hydrate_shared_from_supabase",
            return_value={},
        ),
        patch("orchestrator.graph.health_node", side_effect=lambda s: {**s, **health_out}),
    ):
        result = run_orchestrator(
            message="Sabah ilacımı içtim",
            conversation_id="test-routing-health",
            user_name="Ayşe",
            history=[],
        )

    assert result["routed_agent"] == "health"
    assert result["escalation"] is False


def test_graph_routes_escalation_without_llm():
    from orchestrator.graph import run_orchestrator

    reset_graph_cache()
    with (
        patch(
            "orchestrator.graph.resolve_intent",
            return_value={
                "intent": "escalation",
                "next_node": "escalation",
                "urgency": "high",
                "reason": "düşme",
            },
        ),
        patch("orchestrator.graph.search_memories", return_value=[]),
        patch("orchestrator.graph.build_structured_context", return_value={}),
        patch("orchestrator.graph.hydrate_shared_from_supabase", return_value={}),
        patch("orchestrator.nodes.escalation._try_insert_alert"),
        patch("orchestrator.nodes.escalation._notify_family"),
        patch(
            "orchestrator.nodes.escalation._maybe_sms",
            return_value={"attempted": False, "sent": False},
        ),
    ):
        result = run_orchestrator(
            message="Düştüm kalkamıyorum",
            conversation_id="test-routing-esc",
            elder_id="elder-1",
            user_name="Ayşe",
            history=[],
        )

    assert result["routed_agent"] == "escalation"
    assert result["escalation"] is True


if __name__ == "__main__":
    test_rule_health_routing()
    test_rule_escalation_routing()
    test_rule_companion_leaves_to_llm_or_default()
    test_router_decision_pydantic_accepts_intent_alias()
    test_route_node_sets_active_agent()
    test_orchestrator_router_reads_intent()
    test_graph_routes_health_without_llm()
    test_graph_routes_escalation_without_llm()
    print("OK — agent task routing tests passed")
