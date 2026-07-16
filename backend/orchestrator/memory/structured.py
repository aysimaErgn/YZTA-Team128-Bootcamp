"""Orkestratör için Supabase yapılandırılmış veri erişimi."""

from __future__ import annotations

import re
from typing import Any

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _is_uuid(value: str | None) -> bool:
    return bool(value and _UUID_RE.match(value.strip()))


def get_elder_profile_summary(elder_id: str | None) -> dict[str, Any]:
    if not _is_uuid(elder_id):
        return {}
    try:
        from database import supabase

        result = (
            supabase.table("elders")
            .select("id, full_name, city, preferred_language, notes")
            .eq("id", elder_id)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else {}
    except Exception as error:
        print(f"[STRUCTURED] elder profili alınamadı: {error}")
        return {}


def get_today_medications_summary(elder_id: str | None) -> list[dict[str, Any]]:
    if not _is_uuid(elder_id):
        return []
    try:
        from medication import service as medication_service

        meds = medication_service.list_medications(elder_id, today_only=True)
        summary = []
        for med in meds:
            times = [
                str(s.get("time_of_day", ""))[:5]
                for s in (med.get("medication_schedules") or [])
            ]
            summary.append(
                {
                    "name": med.get("name"),
                    "dosage": med.get("dosage"),
                    "times": times,
                }
            )
        return summary
    except Exception as error:
        print(f"[STRUCTURED] ilaç özeti alınamadı: {error}")
        return []


def get_latest_checkin(conversation_id: str | None) -> dict[str, Any] | None:
    if not conversation_id or len(conversation_id) < 8:
        return None
    try:
        from database import get_today_checkin_status

        return get_today_checkin_status(conversation_id)
    except Exception as error:
        print(f"[STRUCTURED] check-in alınamadı: {error}")
        return None


def build_structured_context(
    elder_id: str | None,
    conversation_id: str | None,
) -> dict[str, Any]:
    return {
        "profile": get_elder_profile_summary(elder_id),
        "todays_medications": get_today_medications_summary(elder_id),
        "latest_checkin": get_latest_checkin(conversation_id),
    }


def format_structured_for_prompt(context: dict[str, Any] | None) -> str:
    if not context:
        return ""

    parts: list[str] = []
    profile = context.get("profile") or {}
    if profile.get("full_name"):
        parts.append(
            f"Profil: {profile.get('full_name')}"
            + (f", {profile['city']}" if profile.get("city") else "")
        )

    meds = context.get("todays_medications") or []
    if meds:
        med_lines = []
        for med in meds[:6]:
            times = ", ".join(med.get("times") or []) or "?"
            med_lines.append(f"{med.get('name')} ({med.get('dosage') or 'doz yok'}) @ {times}")
        parts.append("Bugünkü ilaçlar: " + "; ".join(med_lines))
    else:
        parts.append("Bugünkü ilaçlar: kayıt yok veya yüklenemedi.")

    checkin = context.get("latest_checkin")
    if checkin:
        parts.append(f"Bugünkü check-in: {checkin.get('mood', 'bilinmiyor')}")
    else:
        parts.append("Bugünkü check-in: henüz yok.")

    return "Yapılandırılmış bağlam (Supabase):\n" + "\n".join(f"- {p}" for p in parts) + "\n"
