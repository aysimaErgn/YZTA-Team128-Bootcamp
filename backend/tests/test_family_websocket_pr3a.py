"""PR-3a — aile WebSocket odaları ve CRITICAL_HEALTH_EVENT yayını."""

from __future__ import annotations

import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from routers.websocket import ConnectionManager, notify_family_critical


def test_kiosk_and_family_rooms_are_isolated():
    async def _run():
        mgr = ConnectionManager()
        kiosk = MagicMock()
        kiosk.send_json = AsyncMock()
        family = MagicMock()
        family.send_json = AsyncMock()
        mgr.active_connections["elder-1"] = {"kiosk": [kiosk], "family": [family]}

        await mgr.send_personal_message({"type": "ILAC_HATIRLATMA"}, "elder-1")
        kiosk.send_json.assert_awaited_once()
        family.send_json.assert_not_awaited()

        kiosk.send_json.reset_mock()
        family.send_json.reset_mock()

        count = await mgr.broadcast_to_family(
            "elder-1",
            {"type": "CRITICAL_HEALTH_EVENT", "description": "ağrı 9"},
        )
        assert count == 1
        family.send_json.assert_awaited_once()
        kiosk.send_json.assert_not_awaited()

    asyncio.run(_run())


def test_notify_family_critical_schedules_broadcast():
    with patch("routers.websocket.schedule_coro") as mock_sched:
        notify_family_critical(
            "elder-42",
            description="Ağrı seviyesi 9/10",
            severity="high",
            alert_type="conversation_risk",
            urgency="high",
        )
        mock_sched.assert_called_once()
        coro = mock_sched.call_args[0][0]
        assert asyncio.iscoroutine(coro)
        coro.close()


def test_escalation_node_notifies_family():
    from orchestrator.nodes.escalation import escalation_node

    with (
        patch("orchestrator.nodes.escalation._try_insert_alert"),
        patch("orchestrator.nodes.escalation._notify_family") as mock_notify,
        patch(
            "services.sms_service.resolve_family_contact",
            return_value={"phone": "+905551112233", "sms_enabled": True},
        ),
        patch("services.sms_service.send_family_sms", return_value=True) as mock_sms,
    ):
        state = escalation_node(
            {
                "user_name": "Ahmet",
                "elder_id": "elder-9",
                "user_id": "user-9",
                "user_message": "Düştüm",
                "intent": "escalation",
                "escalation_reason": "Düşme riski",
                "urgency": "high",
            }
        )

    assert state["routed_agent"] == "escalation"
    assert state["escalation_needed"] is True
    mock_notify.assert_called_once_with("elder-9", "Düşme riski", "high")
    mock_sms.assert_called_once()
    assert state["sms_result"]["sent"] is True


if __name__ == "__main__":
    test_kiosk_and_family_rooms_are_isolated()
    test_notify_family_critical_schedules_broadcast()
    test_escalation_node_notifies_family()
    print("OK — PR-3a family websocket tests passed")
