"""WebSocket — kiosk (ilaç) + family (eskalasyon) odaları (PR-3a)."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["websocket"])

VALID_ROLES = frozenset({"kiosk", "family"})

_main_loop: asyncio.AbstractEventLoop | None = None


def set_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Uvicorn startup: scheduler + sync düğümlerden broadcast için."""
    global _main_loop
    _main_loop = loop


def schedule_coro(coro) -> bool:
    """Sync bağlamdan (scheduler / LangGraph) ana loop'a görev bağlar."""
    if not _main_loop or not _main_loop.is_running():
        if asyncio.iscoroutine(coro):
            coro.close()
        print("[WS] Event loop yok; mesaj kuyruğa alınamadı.")
        return False
    asyncio.run_coroutine_threadsafe(coro, _main_loop)
    return True



class ConnectionManager:
    """elder_id → { kiosk: [ws...], family: [ws...] }"""

    def __init__(self) -> None:
        self.active_connections: dict[str, dict[str, list[WebSocket]]] = {}

    async def connect(self, websocket: WebSocket, elder_id: str, role: str = "kiosk") -> None:
        role = role if role in VALID_ROLES else "kiosk"
        await websocket.accept()
        room = self.active_connections.setdefault(elder_id, {"kiosk": [], "family": []})
        room[role].append(websocket)
        print(f"[WS] {elder_id} bağlandı (role={role}).")

    def disconnect(self, websocket: WebSocket, elder_id: str, role: str = "kiosk") -> None:
        role = role if role in VALID_ROLES else "kiosk"
        room = self.active_connections.get(elder_id)
        if not room:
            return
        sockets = room.get(role) or []
        if websocket in sockets:
            sockets.remove(websocket)
        if not room["kiosk"] and not room["family"]:
            del self.active_connections[elder_id]
        print(f"[WS] {elder_id} bağlantısı koptu (role={role}).")

    async def _send_to_role(self, elder_id: str, role: str, message: dict[str, Any]) -> int:
        room = self.active_connections.get(elder_id) or {}
        sockets = list(room.get(role) or [])
        sent = 0
        dead: list[WebSocket] = []
        for websocket in sockets:
            try:
                await websocket.send_json(message)
                sent += 1
            except Exception as error:
                print(f"[WS] {elder_id}/{role} gönderim hatası: {error}")
                dead.append(websocket)
        for websocket in dead:
            self.disconnect(websocket, elder_id, role)
        return sent

    async def send_personal_message(self, message: dict[str, Any], elder_id: str) -> None:
        """Geriye uyum: ilaç hatırlatması → kiosk odası."""
        count = await self._send_to_role(elder_id, "kiosk", message)
        if count:
            print(f"[WS] kiosk/{elder_id} ← {message.get('type', message)}")

    async def broadcast_to_family(self, elder_id: str, message: dict[str, Any]) -> int:
        count = await self._send_to_role(elder_id, "family", message)
        if count:
            print(f"[WS] family/{elder_id} ← {message.get('type', 'event')} ({count})")
        else:
            print(f"[WS] family/{elder_id} dinleyen yok.")
        return count

    def notify_family(self, elder_id: str, message: dict[str, Any]) -> None:
        """Sync çağrı (escalation_node vb.)."""
        if not elder_id:
            return
        schedule_coro(self.broadcast_to_family(elder_id, message))


manager = ConnectionManager()


def notify_family_critical(
    elder_id: str | None,
    *,
    description: str,
    severity: str = "high",
    alert_type: str = "conversation_risk",
    urgency: str | None = None,
) -> None:
    """Eskalasyon / kritik ilaç uyarısını aile odasına yayınlar."""
    if not elder_id:
        return
    payload = {
        "type": "CRITICAL_HEALTH_EVENT",
        "alert_type": alert_type,
        "severity": severity,
        "urgency": urgency or severity,
        "description": description,
        "elder_id": elder_id,
    }
    manager.notify_family(elder_id, payload)


async def _ws_session(websocket: WebSocket, elder_id: str, role: str) -> None:
    role = (role or "kiosk").lower().strip()
    if role not in VALID_ROLES:
        await websocket.close(code=1008)
        return
    await manager.connect(websocket, elder_id, role)
    try:
        while True:
            data = await websocket.receive_text()
            print(f"[WS] {elder_id}/{role} ← {data[:120]}")
    except WebSocketDisconnect:
        manager.disconnect(websocket, elder_id, role)


@router.websocket("/ws/client/{elder_id}")
async def websocket_client(
    websocket: WebSocket,
    elder_id: str,
    role: str = Query(default="kiosk"),
):
    await _ws_session(websocket, elder_id, role)


@router.websocket("/ws/medication/{elder_id}")
async def websocket_medication_legacy(websocket: WebSocket, elder_id: str):
    """Eski kiosk yolu — role=kiosk ile aynı oda."""
    await _ws_session(websocket, elder_id, "kiosk")
