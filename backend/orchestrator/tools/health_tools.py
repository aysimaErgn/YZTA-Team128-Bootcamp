"""
Sağlık ajanı araçları — mevcut medication_logs + checkins şemasına yazar.
"""

from __future__ import annotations

import os
import re
from typing import Any

from database import save_checkin
from medication import service as medication_service
from medication.health_agent import record_manual_taken

HEALTH_PAIN_ESCALATION_THRESHOLD = int(os.getenv("HEALTH_PAIN_ESCALATION_THRESHOLD", "7"))


def _normalize(value: str) -> str:
    text = (value or "").strip().lower()
    replacements = {
        "ı": "i",
        "İ": "i",
        "ş": "s",
        "Ş": "s",
        "ğ": "g",
        "Ğ": "g",
        "ü": "u",
        "Ü": "u",
        "ö": "o",
        "Ö": "o",
        "ç": "c",
        "Ç": "c",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return re.sub(r"\s+", " ", text)


def _names_match(left: str, right: str) -> bool:
    a = _normalize(left)
    b = _normalize(right)
    if not a or not b:
        return False
    return a == b or a in b or b in a


def find_medication_for_elder(elder_id: str, medication_name: str) -> dict[str, Any] | None:
    if not elder_id or not medication_name:
        return None
    try:
        meds = medication_service.list_medications(elder_id, today_only=False)
    except Exception as error:
        print(f"[HEALTH_TOOLS] ilaç listesi alınamadı: {error}")
        return None

    for med in meds:
        if _names_match(med.get("name", ""), medication_name):
            return med
    return None


def record_medication_taken(
    elder_id: str,
    medication_name: str,
    *,
    schedule_id: str | None = None,
) -> dict[str, Any]:
    """İlaç alındı logunu medication_logs tablosuna yazar."""
    if not elder_id:
        return {"ok": False, "message": "Yaşlı profili (elder_id) yok; ilaç kaydedilemedi."}
    if not medication_name:
        return {"ok": False, "message": "İlaç adı belirtilmedi."}

    med = find_medication_for_elder(elder_id, medication_name)
    if not med:
        return {
            "ok": False,
            "message": (
                f"'{medication_name}' adlı aktif ilaç bulunamadı. "
                "İlaçlarım sekmesinden tanımlı adı kullanın."
            ),
        }

    try:
        schedules = med.get("medication_schedules") or []
        resolved_schedule = schedule_id or (schedules[0]["id"] if schedules else None)
        result = record_manual_taken(
            medication_id=med["id"],
            schedule_id=resolved_schedule,
            confirmation_method="orchestrator_chat",
        )
        return {
            "ok": True,
            "message": f"{med.get('name')} alındı olarak kaydedildi.",
            "medication_id": med["id"],
            "log": result.get("log"),
        }
    except Exception as error:
        print(f"[HEALTH_TOOLS] ilaç log hatası: {error}")
        return {"ok": False, "message": "İlaç kaydı yazılamadı."}


def record_daily_checkin(
    conversation_id: str,
    mood: str,
    pain_level: int | None = None,
    notes: str | None = None,
    elder_id: str | None = None,
) -> dict[str, Any]:
    """Günlük check-in kaydı — mood alanına ağrı/not özeti eklenir."""
    if not conversation_id:
        return {"ok": False, "message": "conversation_id yok; check-in kaydedilemedi."}

    mood_label = (mood or "Normal").strip() or "Normal"
    parts = [mood_label]
    if pain_level is not None:
        parts.append(f"ağrı:{int(pain_level)}/10")
    if notes:
        parts.append(str(notes).strip()[:120])
    combined_mood = " | ".join(parts)

    try:
        save_checkin(
            conversation_id=conversation_id,
            mood=combined_mood,
            elder_id=elder_id or None,
        )
        return {
            "ok": True,
            "message": f"Check-in kaydedildi ({combined_mood}).",
            "pain_level": pain_level,
        }
    except Exception as error:
        print(f"[HEALTH_TOOLS] check-in hatası: {error}")
        return {"ok": False, "message": "Check-in kaydedilemedi."}


def should_escalate_health(
    *,
    pain_level: int | None,
    is_danger: bool,
    wrong_medication: bool = False,
    threshold: int | None = None,
) -> tuple[bool, str | None]:
    """Ağrı eşiği / tehlike / yanlış ilaç → eskalasyon kararı."""
    limit = threshold if threshold is not None else HEALTH_PAIN_ESCALATION_THRESHOLD

    if is_danger:
        return True, "Sağlık ajanı tehlikeli semptom/tehlike sinyali tespit etti."
    if wrong_medication:
        return True, "Yanlış veya şüpheli ilaç beyanı."
    if pain_level is not None and int(pain_level) >= limit:
        return True, f"Ağrı seviyesi {pain_level}/10 (eşik {limit})."
    return False, None
