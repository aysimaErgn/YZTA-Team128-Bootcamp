"""Ajanlar arası veri paylaşımı — shared_health_context + companion tüketimi."""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from orchestrator.memory.shared import (
    build_shared_from_health_decision,
    format_shared_health_for_prompt,
    hydrate_shared_from_supabase,
    parse_mood_label,
    parse_pain_from_text,
)


def test_parse_pain_and_mood_from_checkin_string():
    assert parse_pain_from_text("Halsiz | ağrı:5/10 | bel") == 5
    assert parse_mood_label("Halsiz | ağrı:5/10") == "Halsiz"


def test_health_decision_writes_shared_context():
    shared = build_shared_from_health_decision(
        {
            "mood": "Halsiz/Endişeli",
            "pain_level": 5,
            "is_danger": False,
            "notes": "hafif baş ağrısı",
        }
    )
    assert shared["last_pain_level"] == 5
    assert shared["detected_mood"] == "Halsiz/Endişeli"
    assert shared["source"] == "health_agent"
    assert shared["is_danger"] is False


def test_companion_prompt_includes_shared_health():
    text = format_shared_health_for_prompt(
        {
            "detected_mood": "Halsiz",
            "shared_health_context": {
                "last_pain_level": 5,
                "detected_mood": "Halsiz",
                "medication_missed": False,
                "source": "health_agent",
                "notes": "baş ağrısı",
            },
        }
    )
    assert "Halsiz" in text
    assert "5/10" in text
    assert "Ajanlar arası" in text


def test_hydrate_uses_checkin_history():
    fake_rows = [
        {
            "mood": "Halsiz | ağrı:5/10",
            "created_at": "2099-01-01T12:00:00+00:00",
        }
    ]
    with patch("database.get_checkin_history", return_value=fake_rows):
        shared = hydrate_shared_from_supabase("test-share-conv-1", elder_id=None)

    assert shared["last_pain_level"] == 5
    assert shared["detected_mood"] == "Halsiz"
    assert shared["source"] == "supabase"


def test_health_node_sets_shared_fields():
    from orchestrator.nodes.health import health_node

    fake_decision = MagicMock()
    fake_decision.choices = [
        MagicMock(
            message=MagicMock(
                content=(
                    '{"action":"log_health","medication_name":null,'
                    '"pain_level":5,"mood":"Halsiz","notes":"baş ağrısı",'
                    '"is_danger":false,"wrong_medication":false}'
                )
            )
        )
    ]
    fake_reply = MagicMock()
    fake_reply.choices = [MagicMock(message=MagicMock(content="Not ettim."))]

    with (
        patch("orchestrator.nodes.health._client") as mock_client,
        patch(
            "orchestrator.nodes.health.record_daily_checkin",
            return_value={"ok": True, "message": "Check-in kaydedildi.", "pain_level": 5},
        ),
        patch("orchestrator.nodes.health.extract_and_store_memories", return_value=[]),
    ):
        mock_client.return_value.chat.completions.create.side_effect = [
            fake_decision,
            fake_reply,
        ]
        state = health_node(
            {
                "user_message": "Biraz başım ağrıyor, ağrı 5, halsizim.",
                "user_name": "Ayşe",
                "elder_id": "elder-1",
                "conversation_id": "conv-1",
                "chat_history": [],
                "retrieved_memories": [],
                "structured_context": {},
                "shared_health_context": {},
            }
        )

    assert state["active_agent"] == "health"
    assert state["detected_mood"] == "Halsiz"
    assert state["shared_health_context"]["last_pain_level"] == 5
    assert state["escalation_needed"] is False


def test_companion_node_receives_shared_in_system_prompt():
    from orchestrator.nodes.companion import companion_node

    captured = {}

    def fake_create(**kwargs):
        captured["messages"] = kwargs["messages"]
        mock = MagicMock()
        mock.choices = [MagicMock(message=MagicMock(content="Halini sordum."))]
        return mock

    with (
        patch("orchestrator.nodes.companion._client") as mock_client,
        patch("orchestrator.nodes.companion.extract_and_store_memories", return_value=[]),
    ):
        mock_client.return_value.chat.completions.create.side_effect = fake_create
        out = companion_node(
            {
                "user_message": "Biraz sohbet edelim.",
                "user_name": "Ayşe",
                "elder_id": "elder-1",
                "detected_mood": "Halsiz",
                "shared_health_context": {
                    "last_pain_level": 5,
                    "detected_mood": "Halsiz",
                    "source": "health_agent",
                },
                "chat_history": [],
                "retrieved_memories": [],
                "structured_context": {},
            }
        )

    system = captured["messages"][0]["content"]
    assert "Halsiz" in system
    assert "5/10" in system or "ağrı" in system.lower()
    assert out["routed_agent"] == "companion"
    assert out["active_agent"] == "companion"


if __name__ == "__main__":
    test_parse_pain_and_mood_from_checkin_string()
    test_health_decision_writes_shared_context()
    test_companion_prompt_includes_shared_health()
    test_hydrate_uses_checkin_history()
    test_health_node_sets_shared_fields()
    test_companion_node_receives_shared_in_system_prompt()
    print("OK — inter-agent shared context tests passed")
