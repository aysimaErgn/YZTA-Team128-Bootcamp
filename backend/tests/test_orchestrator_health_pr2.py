"""Orkestratör PR-2 — sağlık araçları, ağrı eşiği, health→escalation kenarı."""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from orchestrator.graph import check_health_escalation, reset_graph_cache
from orchestrator.tools.health_tools import (
    HEALTH_PAIN_ESCALATION_THRESHOLD,
    should_escalate_health,
)


def test_pain_threshold_default_is_seven():
    assert HEALTH_PAIN_ESCALATION_THRESHOLD == 7


def test_should_escalate_at_threshold():
    ok, reason = should_escalate_health(pain_level=7, is_danger=False)
    assert ok is True
    assert "7" in (reason or "")

    ok_low, _ = should_escalate_health(pain_level=6, is_danger=False)
    assert ok_low is False

    ok_danger, reason_d = should_escalate_health(pain_level=2, is_danger=True)
    assert ok_danger is True
    assert "tehlike" in (reason_d or "").lower() or "tehlike" in (reason_d or "")


def test_check_health_escalation_edge():
    assert check_health_escalation({"escalation_needed": True}) == "escalation"
    assert check_health_escalation({"escalation_needed": False}) == "end"
    assert check_health_escalation({}) == "end"


def test_health_node_medication_no_escalation():
    """Normal akış: ilaç onayı → tool çağrılır, escalation_needed False."""
    from orchestrator.nodes.health import health_node

    fake_decision = MagicMock()
    fake_decision.choices = [
        MagicMock(
            message=MagicMock(
                content=(
                    '{"action":"confirm_medication","medication_name":"Apranax",'
                    '"pain_level":null,"mood":null,"notes":null,'
                    '"is_danger":false,"wrong_medication":false}'
                )
            )
        )
    ]
    fake_reply = MagicMock()
    fake_reply.choices = [MagicMock(message=MagicMock(content="Kaydettim, aferin."))]

    with (
        patch("orchestrator.nodes.health._client") as mock_client,
        patch(
            "orchestrator.nodes.health.record_medication_taken",
            return_value={"ok": True, "message": "Apranax alındı olarak kaydedildi."},
        ) as mock_med,
        patch("orchestrator.nodes.health.extract_and_store_memories", return_value=[]),
    ):
        mock_client.return_value.chat.completions.create.side_effect = [
            fake_decision,
            fake_reply,
        ]
        state = health_node(
            {
                "user_message": "Sabah ilacım olan Apranax'ı az önce içtim.",
                "user_name": "Ayşe Teyze",
                "elder_id": "elder-1",
                "conversation_id": "conv-1",
                "chat_history": [],
                "retrieved_memories": [],
                "structured_context": {},
            }
        )

    mock_med.assert_called_once()
    assert state["escalation_needed"] is False
    assert state["routed_agent"] == "health"
    assert "Apranax" in " ".join(state.get("health_tool_results") or [])


def test_health_node_high_pain_sets_escalation():
    """Eskalasyon: ağrı 8 → check-in + escalation_needed True."""
    from orchestrator.nodes.health import health_node

    fake_decision = MagicMock()
    fake_decision.choices = [
        MagicMock(
            message=MagicMock(
                content=(
                    '{"action":"log_health","medication_name":null,'
                    '"pain_level":8,"mood":"kötü","notes":"bel ağrısı",'
                    '"is_danger":false,"wrong_medication":false}'
                )
            )
        )
    ]
    fake_reply = MagicMock()
    fake_reply.choices = [
        MagicMock(message=MagicMock(content="Anlıyorum, not ettim."))
    ]

    with (
        patch("orchestrator.nodes.health._client") as mock_client,
        patch(
            "orchestrator.nodes.health.record_daily_checkin",
            return_value={"ok": True, "message": "Check-in kaydedildi.", "pain_level": 8},
        ) as mock_checkin,
        patch("orchestrator.nodes.health.extract_and_store_memories", return_value=[]),
    ):
        mock_client.return_value.chat.completions.create.side_effect = [
            fake_decision,
            fake_reply,
        ]
        state = health_node(
            {
                "user_message": "Belim çok kötü ağrıyor, ağrı seviyem 8.",
                "user_name": "Ayşe Teyze",
                "elder_id": "elder-1",
                "conversation_id": "conv-1",
                "chat_history": [],
                "retrieved_memories": [],
                "structured_context": {},
            }
        )

    mock_checkin.assert_called_once()
    assert state["escalation_needed"] is True
    assert state["urgency"] == "high"
    assert "8" in (state.get("escalation_reason") or "")


def test_graph_health_to_escalation_path():
    """Graph: health escalation_needed → escalation düğümü son yanıtı üretir."""
    from orchestrator.graph import run_orchestrator

    reset_graph_cache()

    health_out = {
        "agent_response": "Not ettim.",
        "routed_agent": "health",
        "escalation_needed": True,
        "escalation_reason": "Ağrı seviyesi 8/10 (eşik 7).",
        "urgency": "high",
        "memories_stored": [],
        "health_decision": {"pain_level": 8},
        "health_tool_results": ["Check-in kaydedildi."],
    }

    with (
        patch("orchestrator.graph.resolve_intent", return_value={"intent": "health", "urgency": "low"}),
        patch("orchestrator.graph.search_memories", return_value=[]),
        patch("orchestrator.graph.build_structured_context", return_value={}),
        patch("orchestrator.graph.health_node", side_effect=lambda s: {**s, **health_out}),
        patch("orchestrator.nodes.escalation._try_insert_alert"),
    ):
        result = run_orchestrator(
            message="Belim çok kötü ağrıyor, ağrı seviyem 8.",
            conversation_id="test-conv-pr2",
            elder_id="elder-test",
            user_name="Ayşe Teyze",
            history=[],
        )

    assert result["escalation"] is True
    assert result["routed_agent"] == "escalation"
    assert "bilgilendir" in result["ai_response"].lower() or "Yakınlarını" in result["ai_response"]


def test_graph_medication_ends_without_escalation():
    from orchestrator.graph import run_orchestrator

    reset_graph_cache()

    health_out = {
        "agent_response": "Kaydettim.",
        "routed_agent": "health",
        "escalation_needed": False,
        "escalation_reason": None,
        "urgency": "low",
        "memories_stored": [],
        "health_decision": {"action": "confirm_medication"},
        "health_tool_results": ["Apranax alındı olarak kaydedildi."],
    }

    with (
        patch("orchestrator.graph.resolve_intent", return_value={"intent": "health", "urgency": "low"}),
        patch("orchestrator.graph.search_memories", return_value=[]),
        patch("orchestrator.graph.build_structured_context", return_value={}),
        patch("orchestrator.graph.health_node", side_effect=lambda s: {**s, **health_out}),
    ):
        result = run_orchestrator(
            message="Sabah ilacım olan Apranax'ı az önce içtim.",
            conversation_id="test-conv-pr2-med",
            elder_id="elder-test",
            user_name="Ayşe Teyze",
            history=[],
        )

    assert result["escalation"] is False
    assert result["routed_agent"] == "health"


if __name__ == "__main__":
    test_pain_threshold_default_is_seven()
    test_should_escalate_at_threshold()
    test_check_health_escalation_edge()
    test_health_node_medication_no_escalation()
    test_health_node_high_pain_sets_escalation()
    test_graph_health_to_escalation_path()
    test_graph_medication_ends_without_escalation()
    print("OK — orchestrator PR-2 health/escalation tests passed")
