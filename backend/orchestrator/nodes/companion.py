"""Refakat Ajanı — kısa + uzun süreli ortak hafızayı kullanır."""

from __future__ import annotations

import os

from groq import Groq

from orchestrator.memory.long_term import (
    extract_and_store_memories,
    format_memories_for_prompt,
)
from orchestrator.memory.structured import format_structured_for_prompt
from orchestrator.prompts import COMPANION_SYSTEM
from orchestrator.state import AgentState


def _client() -> Groq:
    return Groq(api_key=os.environ.get("GROQ_API_KEY"))


def companion_node(state: AgentState) -> AgentState:
    user_name = state.get("user_name") or "canım"
    memory_block = format_memories_for_prompt(state.get("retrieved_memories") or [])
    structured_block = format_structured_for_prompt(state.get("structured_context"))

    system = (
        f"{COMPANION_SYSTEM} Karşındaki kişinin adı: {user_name}.\n"
        f"{memory_block}"
        f"{structured_block}"
        "Hafızadaki bilgileri doğal kullan; uydurma. Tıbbi teşhis verme."
    )

    messages: list[dict] = [{"role": "system", "content": system}]
    for item in state.get("chat_history") or []:
        role = item.get("role")
        content = item.get("content")
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": state.get("user_message", "")})

    try:
        response = _client().chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=messages,
            max_tokens=150,
            temperature=0.7,
        )
        reply = (response.choices[0].message.content or "").strip()
    except Exception as error:
        print(f"[COMPANION] Hata: {error}")
        reply = f"{user_name}, şu an seni duyuyorum. Birazdan tekrar konuşalım olur mu?"

    stored = extract_and_store_memories(
        state.get("elder_id") or "",
        state.get("user_message") or "",
    )

    return {
        **state,
        "agent_response": reply,
        "routed_agent": "companion",
        "escalation_needed": False,
        "memories_stored": stored,
    }
