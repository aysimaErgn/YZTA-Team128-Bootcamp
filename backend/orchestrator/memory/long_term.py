"""Uzun süreli hafıza — Chroma (onnx gerekmeyen hashing embedding) veya JSON yedek."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import uuid
from pathlib import Path
from typing import Any

_MEMORY_DIR = Path(__file__).resolve().parent / "data"
_CHROMA_DIR = _MEMORY_DIR / "chroma"
_JSON_FALLBACK = _MEMORY_DIR / "memories.json"
_EMBED_DIM = 128

_collection = None
_use_chroma: bool | None = None


class _HashEmbeddingFunction:
    """onnxruntime gerektirmeyen hafif yerel embedding (bootcamp / Windows uyumlu)."""

    def name(self) -> str:
        return "yanimda_hash_v1"

    def __call__(self, input: list[str]) -> list[list[float]]:
        return [_hash_embed(text) for text in input]


def _hash_embed(text: str) -> list[float]:
    vec = [0.0] * _EMBED_DIM
    tokens = re.findall(r"[a-zA-ZçğıöşüÇĞİÖŞÜ0-9]+", (text or "").lower())
    if not tokens:
        tokens = ["bos"]
    for token in tokens:
        digest = hashlib.md5(token.encode("utf-8")).hexdigest()
        idx = int(digest[:8], 16) % _EMBED_DIM
        sign = 1.0 if int(digest[8:10], 16) % 2 == 0 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _ensure_dirs() -> None:
    _MEMORY_DIR.mkdir(parents=True, exist_ok=True)


def _init_chroma():
    global _collection, _use_chroma
    if _use_chroma is not None:
        return _collection

    # Windows/Anaconda'da chromadb native crash riski — varsayılan kapalı
    if os.getenv("MEMORY_USE_CHROMA", "false").lower() not in {"1", "true", "yes", "on"}:
        _use_chroma = False
        _collection = None
        print("[MEMORY] JSON uzun süreli hafıza aktif (MEMORY_USE_CHROMA=true ile Chroma denenebilir).")
        return None

    try:
        import chromadb
        from chromadb.config import Settings

        _ensure_dirs()
        client = chromadb.PersistentClient(
            path=str(_CHROMA_DIR),
            settings=Settings(anonymized_telemetry=False),
        )
        collection = client.get_or_create_collection(
            name="yanimda_elder_memories_v2",
            metadata={"hnsw:space": "cosine"},
            embedding_function=_HashEmbeddingFunction(),
        )
        probe_id = f"probe-{uuid.uuid4()}"
        collection.add(ids=[probe_id], documents=["probe"], metadatas=[{"elder_id": "__probe__"}])
        collection.delete(ids=[probe_id])

        _collection = collection
        _use_chroma = True
        print("[MEMORY] Chroma uzun süreli hafıza hazır (hash embedding).")
        return _collection
    except Exception as error:
        _use_chroma = False
        _collection = None
        print(f"[MEMORY] Chroma kullanılamadı, JSON yedek aktif: {error}")
        return None


def _disable_chroma(reason: str) -> None:
    global _collection, _use_chroma
    _use_chroma = False
    _collection = None
    print(f"[MEMORY] Chroma kapatıldı, JSON yedek: {reason}")


def _load_json_store() -> dict[str, list[dict[str, Any]]]:
    _ensure_dirs()
    if not _JSON_FALLBACK.exists():
        return {}
    try:
        return json.loads(_JSON_FALLBACK.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_json_store(store: dict[str, list[dict[str, Any]]]) -> None:
    _ensure_dirs()
    _JSON_FALLBACK.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-ZçğıöşüÇĞİÖŞÜ0-9]+", (text or "").lower()))


def _json_search(elder_id: str, query: str, limit: int) -> list[str]:
    store = _load_json_store()
    items = store.get(elder_id or "anonymous", [])
    if not items:
        return []
    query_tokens = _tokenize(query)
    if not query_tokens:
        return [item["text"] for item in items[-limit:]]

    scored: list[tuple[int, str]] = []
    for item in items:
        text = item.get("text", "")
        overlap = len(query_tokens & _tokenize(text))
        scored.append((overlap, text))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [text for score, text in scored if score > 0][:limit] or [i["text"] for i in items[-limit:]]


def add_memory(
    elder_id: str,
    text: str,
    *,
    category: str = "general",
    metadata: dict[str, Any] | None = None,
) -> bool:
    """Kullanıcıya ait bir anıyı / ilgi alanını kaydeder."""
    content = (text or "").strip()
    if not content or len(content) < 8:
        return False

    key = elder_id or "anonymous"
    meta = {"elder_id": key, "category": category, **(metadata or {})}
    memory_id = str(uuid.uuid4())

    collection = _init_chroma()
    if _use_chroma and collection is not None:
        try:
            collection.add(
                ids=[memory_id],
                documents=[content],
                metadatas=[meta],
            )
            return True
        except Exception as error:
            _disable_chroma(str(error))

    store = _load_json_store()
    store.setdefault(key, []).append({"id": memory_id, "text": content, "metadata": meta})
    # Elder başına son 100 anı
    store[key] = store[key][-100:]
    _save_json_store(store)
    return True


def search_memories(elder_id: str, query: str, limit: int = 5) -> list[str]:
    """Sorguya en yakın uzun süreli anıları döner."""
    key = elder_id or "anonymous"
    collection = _init_chroma()
    if _use_chroma and collection is not None:
        try:
            where = {"elder_id": key}
            result = collection.query(
                query_texts=[query or "genel"],
                n_results=limit,
                where=where,
            )
            docs = (result.get("documents") or [[]])[0]
            return [doc for doc in docs if doc]
        except Exception as error:
            _disable_chroma(str(error))

    return _json_search(key, query, limit)


def extract_and_store_memories(elder_id: str, user_message: str) -> list[str]:
    """
    Kullanıcı mesajından basit ilgi / alışkanlık cümlelerini çıkarır ve kaydeder.
    LLM şart değil — kural tabanlı (bootcamp MVP).
    """
    text = (user_message or "").strip()
    if not text:
        return []

    patterns = [
        r"(.+?)\s*(severim|hoşlanırım|bayılırım)",
        r"hobim\s+(.+)",
        r"her\s+(sabah|akşam|gün)\s+(.+)",
        r"(.+?)\s*(içerim|yerim|dinlerim|izlerim)",
        r"torunum(?:un|larım)?\s+(.+)",
        r"eski\s+mesleğim\s+(.+)",
    ]

    stored: list[str] = []
    lowered = text.lower()
    # Tek cümlelik anlamlı paylaşımları da sakla
    if len(text) >= 20 and any(
        key in lowered
        for key in ["severim", "hobim", "torun", "eskiden", "alışkan", "her gün", "her sabah"]
    ):
        if add_memory(elder_id, text, category="preference"):
            stored.append(text)

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            snippet = match.group(0).strip()
            if snippet and add_memory(elder_id, snippet, category="preference"):
                stored.append(snippet)

    return stored


def format_memories_for_prompt(memories: list[str]) -> str:
    if not memories:
        return ""
    lines = "\n".join(f"- {item}" for item in memories)
    return f"Kullanıcı hakkında bilinenler (uzun süreli hafıza):\n{lines}\n"


def memory_backend_name() -> str:
    _init_chroma()
    return "chroma" if _use_chroma else "json_fallback"
