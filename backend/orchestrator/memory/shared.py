"""Ajanlar arası paylaşılan sağlık / ruh hali bağlamı (State + Supabase)."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

_PAIN_RE = re.compile(r"(?:ağr[ıi]|agri)\s*:?\s*(\d{1,2})\s*(?:/10)?", re.IGNORECASE)


def parse_pain_from_text(text: str | None) -> int | None:
    if not text:
        return None
    match = _PAIN_RE.search(str(text))
    if not match:
        return None
    try:
        return max(0, min(10, int(match.group(1))))
    except ValueError:
        return None


def parse_mood_label(mood_raw: str | None) -> str:
    """Check-in mood alanından ilk etiket (örn. 'Halsiz | ağrı:5/10' → Halsiz)."""
    if not mood_raw:
        return "Nötr"
    first = str(mood_raw).split("|")[0].strip()
    return first or "Nötr"


def empty_shared_health_context() -> dict[str, Any]:
    return {
        "last_pain_level": None,
        "detected_mood": "Nötr",
        "medication_missed": False,
        "wrong_medication": False,
        "is_danger": False,
        "notes": None,
        "source": None,
        "timestamp": None,
        "recent_checkins": [],
    }


# Aynı process içinde turlar arası paylaşım (DB fail olsa bile)
_SESSION_SHARED: dict[str, dict[str, Any]] = {}


def remember_shared_context(
    conversation_id: str | None,
    shared: dict[str, Any] | None,
    mood: str | None = None,
) -> None:
    if not conversation_id or not shared:
        return
    _SESSION_SHARED[str(conversation_id)] = {
        "shared_health_context": dict(shared),
        "detected_mood": mood or shared.get("detected_mood") or "Nötr",
    }


def recall_shared_context(conversation_id: str | None) -> dict[str, Any]:
    if not conversation_id:
        return {}
    return dict(_SESSION_SHARED.get(str(conversation_id)) or {})


def build_shared_from_health_decision(
    decision: dict[str, Any] | None,
    *,
    previous: dict[str, Any] | None = None,
    tool_ok: bool = True,
) -> dict[str, Any]:
    """Sağlık ajanı turunda State'e yazılacak ortak bağlam."""
    base = {**empty_shared_health_context(), **(previous or {})}
    decision = decision or {}

    mood = decision.get("mood")
    if mood:
        base["detected_mood"] = str(mood).strip() or base.get("detected_mood") or "Nötr"

    pain = decision.get("pain_level")
    if pain is not None:
        try:
            base["last_pain_level"] = max(0, min(10, int(pain)))
        except (TypeError, ValueError):
            pass

    if decision.get("is_danger"):
        base["is_danger"] = True
    if decision.get("wrong_medication"):
        base["wrong_medication"] = True

    notes = decision.get("notes")
    if notes:
        base["notes"] = str(notes)[:200]

    base["source"] = "health_agent"
    base["timestamp"] = datetime.now(timezone.utc).isoformat()
    base["tool_logged"] = tool_ok
    return base


def hydrate_shared_from_supabase(
    conversation_id: str | None,
    elder_id: str | None = None,
    *,
    days: int = 3,
    limit: int = 10,
) -> dict[str, Any]:
    """
    Kalıcı paylaşım: son check-in'lerden shared_health_context üretir.
    Böylece bir sonraki companion turu sağlık bulgularını görür.
    """
    shared = empty_shared_health_context()
    shared["source"] = "supabase"

    if not conversation_id or not str(conversation_id).strip():
        return shared

    try:
        from database import get_checkin_history

        rows = get_checkin_history(conversation_id, limit=limit) or []
    except Exception as error:
        # Test UUID'si olmayan id'lerde gürültüyü azalt
        err = str(error)
        if "invalid input syntax for type uuid" not in err:
            print(f"[SHARED] check-in geçmişi alınamadı: {error}")
        rows = []

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    recent: list[dict[str, Any]] = []
    for row in rows:
        created = row.get("created_at")
        mood = row.get("mood") or ""
        entry = {
            "mood": mood,
            "mood_label": parse_mood_label(mood),
            "pain_level": parse_pain_from_text(mood),
            "created_at": created,
        }
        # Tarih parse edilemezse yine de son kayıtları tut
        keep = True
        if created:
            try:
                ts = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
                keep = ts >= cutoff
            except ValueError:
                keep = True
        if keep:
            recent.append(entry)

    shared["recent_checkins"] = recent[:5]

    if recent:
        latest = recent[0]
        shared["detected_mood"] = latest.get("mood_label") or "Nötr"
        shared["last_pain_level"] = latest.get("pain_level")
        shared["timestamp"] = latest.get("created_at")
        shared["notes"] = latest.get("mood")

    # İlaç kaçırma / yanlış ilaç alert'leri
    if elder_id:
        try:
            from medication import service as medication_service

            alerts = medication_service.get_elder_alerts(elder_id, limit=5) or []
            for alert in alerts:
                atype = (alert.get("alert_type") or "").lower()
                if atype == "medication_missed":
                    shared["medication_missed"] = True
                if "wrong" in atype:
                    shared["wrong_medication"] = True
        except Exception as error:
            print(f"[SHARED] alert okunamadı: {error}")

    return shared


def merge_shared_prefer_live(
    hydrated: dict[str, Any] | None,
    live: dict[str, Any] | None,
) -> dict[str, Any]:
    """Aynı turda live (health yazımı) varsa onu önceliklendir."""
    base = {**empty_shared_health_context(), **(hydrated or {})}
    if not live:
        return base
    if live.get("source") == "health_agent" or live.get("timestamp"):
        merged = {**base, **live}
        # recent_checkins hydrate'den gelsin
        if hydrated and hydrated.get("recent_checkins") and not live.get("recent_checkins"):
            merged["recent_checkins"] = hydrated["recent_checkins"]
        return merged
    return base


def format_shared_health_for_prompt(state: dict[str, Any] | None) -> str:
    """Refakat (ve diğer) ajanlar için ortak bağlam metni."""
    if not state:
        return ""

    shared = state.get("shared_health_context") or {}
    mood = state.get("detected_mood") or shared.get("detected_mood") or "Nötr"
    pain = shared.get("last_pain_level")
    parts = [
        f"Algılanan ruh hali (sağlık/ortak bellek): {mood}",
    ]
    if pain is not None:
        parts.append(f"Son bildirilen ağrı: {pain}/10")
    if shared.get("medication_missed"):
        parts.append("Uyarı: yakın zamanda ilaç kaçırma kaydı var.")
    if shared.get("wrong_medication"):
        parts.append("Uyarı: yanlış ilaç sinyali var.")
    if shared.get("is_danger"):
        parts.append("Uyarı: sağlık ajanı tehlike sinyali işaretlemiş.")
    if shared.get("notes") and shared.get("source") == "health_agent":
        parts.append(f"Sağlık notu: {shared['notes']}")

    recent = shared.get("recent_checkins") or []
    if recent:
        brief = []
        for item in recent[:3]:
            label = item.get("mood_label") or "?"
            p = item.get("pain_level")
            brief.append(f"{label}" + (f" (ağrı {p})" if p is not None else ""))
        parts.append("Son check-in özeti: " + "; ".join(brief))

    guidance = (
        "Bu bilgileri tıbbi teşhis gibi kullanma. "
        "Doğrudan 'ağrın 5' demeden, nazikçe hal hatır sor; "
        "kullanıcı iyi görünüyorsa eski anılara veya hobilerine de değinebilirsin."
    )
    return (
        "Ajanlar arası paylaşılan sağlık bağlamı:\n"
        + "\n".join(f"- {p}" for p in parts)
        + f"\n- {guidance}\n"
    )
