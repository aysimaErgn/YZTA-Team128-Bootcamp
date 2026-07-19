"""Kısa süreli hafıza — Supabase sohbet geçmişi."""

from typing import Any

from database import get_conversation_history


def load_recent_messages(conversation_id: str, limit: int = 10) -> list[dict[str, Any]]:
    if not conversation_id:
        return []

    try:
        history = get_conversation_history(conversation_id) or []
        trimmed = history[-limit:]
        return [
            {"role": item.get("role", "user"), "content": item.get("content", "")}
            for item in trimmed
            if item.get("content")
        ]
    except Exception as error:
        print(f"[ORCHESTRATOR] Geçmiş yüklenemedi: {error}")
        return []
