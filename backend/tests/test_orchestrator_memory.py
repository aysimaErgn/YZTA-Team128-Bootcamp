"""Aşama 2 — uzun süreli hafıza testleri (Chroma veya JSON yedek)."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from orchestrator.memory.long_term import (
    add_memory,
    extract_and_store_memories,
    memory_backend_name,
    search_memories,
)
from orchestrator.router import rule_based_intent


def test_add_and_search_memory():
    elder_id = "test-elder-memory-1"
    assert add_memory(elder_id, "Torunumla satranç oynamayı severim", category="preference")
    hits = search_memories(elder_id, "satranç torun", limit=3)
    assert any("satranç" in h.lower() or "torun" in h.lower() for h in hits), hits
    print("memory backend:", memory_backend_name())


def test_extract_preference_sentence():
    elder_id = "test-elder-memory-2"
    stored = extract_and_store_memories(elder_id, "Her sabah çay içerim ve bahçeyi severim")
    assert stored
    hits = search_memories(elder_id, "çay bahçe", limit=5)
    assert hits


def test_router_still_works():
    assert rule_based_intent("Düştüm kalkamıyorum") == "escalation"
    assert rule_based_intent("İlacımı içtim") == "health"


if __name__ == "__main__":
    test_add_and_search_memory()
    test_extract_preference_sentence()
    test_router_still_works()
    print("OK — memory stage-2 tests passed")
