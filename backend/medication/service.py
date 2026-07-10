from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from database import supabase

LOCAL_TZ = ZoneInfo("Europe/Istanbul")
DEMO_ELDER_NAME = "Demo Ahmet Amca (Test)"
DEMO_USER_ID = "kiosk-demo-user"


def parse_time_of_day(value: str) -> time:
    parts = value.strip().split(":")
    hour = int(parts[0])
    minute = int(parts[1])
    second = int(parts[2]) if len(parts) > 2 else 0
    return time(hour, minute, second)


def normalize_time_of_day(value: str) -> str:
    return parse_time_of_day(value).strftime("%H:%M:%S")


def get_local_weekday() -> int:
    return datetime.now(LOCAL_TZ).isoweekday()


def resolve_elder_for_user(user_id: str, user_name: str) -> dict[str, Any]:
    by_id = supabase.table("elders").select("*").eq("id", user_id).limit(1).execute()
    if by_id.data:
        return by_id.data[0]

    by_notes = (
        supabase.table("elders")
        .select("*")
        .ilike("notes", f"%{user_id}%")
        .limit(1)
        .execute()
    )
    if by_notes.data:
        return by_notes.data[0]

    by_name = (
        supabase.table("elders")
        .select("*")
        .ilike("full_name", user_name.strip())
        .limit(1)
        .execute()
    )
    if by_name.data:
        return by_name.data[0]

    created = (
        supabase.table("elders")
        .insert(
            {
                "full_name": user_name.strip(),
                "preferred_language": "tr",
                "notes": f"users tablosu user_id: {user_id}",
            }
        )
        .execute()
        .data[0]
    )
    return created


def list_medications(elder_id: str, today_only: bool = False) -> list[dict[str, Any]]:
    medications = (
        supabase.table("medications")
        .select("*, medication_schedules(*)")
        .eq("elder_id", elder_id)
        .eq("is_active", True)
        .order("created_at")
        .execute()
        .data
    )

    if not today_only:
        return medications

    weekday = get_local_weekday()
    filtered: list[dict[str, Any]] = []
    for medication in medications:
        schedules = medication.get("medication_schedules") or []
        todays_schedules = [
            schedule
            for schedule in schedules
            if weekday in (schedule.get("days_of_week") or [1, 2, 3, 4, 5, 6, 7])
        ]
        if todays_schedules:
            medication = dict(medication)
            medication["medication_schedules"] = todays_schedules
            filtered.append(medication)
    return filtered


def get_medication(medication_id: str) -> dict[str, Any] | None:
    result = supabase.table("medications").select("*").eq("id", medication_id).limit(1).execute()
    return result.data[0] if result.data else None


def create_medication(
    elder_id: str,
    name: str,
    dosage: str | None,
    form: str | None,
    notes: str | None,
    schedules: list[dict[str, Any]],
) -> dict[str, Any]:
    medication = (
        supabase.table("medications")
        .insert(
            {
                "elder_id": elder_id,
                "name": name.strip(),
                "dosage": dosage,
                "form": form,
                "notes": notes,
                "is_active": True,
            }
        )
        .execute()
        .data[0]
    )

    created_schedules: list[dict[str, Any]] = []
    if schedules:
        rows = [
            {
                "medication_id": medication["id"],
                "time_of_day": normalize_time_of_day(item["time_of_day"]),
                "days_of_week": item.get("days_of_week") or [1, 2, 3, 4, 5, 6, 7],
            }
            for item in schedules
        ]
        created_schedules = supabase.table("medication_schedules").insert(rows).execute().data

    medication["medication_schedules"] = created_schedules
    return medication


def update_medication(
    medication_id: str,
    name: str | None = None,
    dosage: str | None = None,
    form: str | None = None,
    notes: str | None = None,
    is_active: bool | None = None,
) -> dict[str, Any]:
    payload = {
        key: value
        for key, value in {
            "name": name.strip() if name else None,
            "dosage": dosage,
            "form": form,
            "notes": notes,
            "is_active": is_active,
        }.items()
        if value is not None
    }

    if not payload:
        medication = get_medication(medication_id)
        if not medication:
            raise ValueError("İlaç bulunamadı.")
        return medication

    return supabase.table("medications").update(payload).eq("id", medication_id).execute().data[0]


def deactivate_medication(medication_id: str) -> dict[str, Any]:
    return update_medication(medication_id, is_active=False)


def add_schedule(
    medication_id: str,
    time_of_day: str,
    days_of_week: list[int] | None = None,
) -> dict[str, Any]:
    return (
        supabase.table("medication_schedules")
        .insert(
            {
                "medication_id": medication_id,
                "time_of_day": normalize_time_of_day(time_of_day),
                "days_of_week": days_of_week or [1, 2, 3, 4, 5, 6, 7],
            }
        )
        .execute()
        .data[0]
    )


def delete_schedule(schedule_id: str) -> None:
    supabase.table("medication_schedules").delete().eq("id", schedule_id).execute()


def now_local() -> datetime:
    return datetime.now(LOCAL_TZ)


def today_start_iso() -> str:
    return now_local().strftime("%Y-%m-%dT00:00:00")


def build_scheduled_at(schedule_id: str | None) -> str:
    now = now_local()
    if not schedule_id:
        return now.isoformat()

    schedule_res = (
        supabase.table("medication_schedules")
        .select("time_of_day")
        .eq("id", schedule_id)
        .limit(1)
        .execute()
    )
    if schedule_res.data:
        time_str = schedule_res.data[0].get("time_of_day", "")
        return f"{now.strftime('%Y-%m-%d')}T{time_str}"
    return now.isoformat()


def get_today_logs_for_medication(medication_id: str) -> list[dict[str, Any]]:
    response = (
        supabase.table("medication_logs")
        .select("*")
        .eq("medication_id", medication_id)
        .gte("scheduled_at", today_start_iso())
        .execute()
    )
    return response.data or []


def has_schedule_been_resolved_today(medication_id: str, schedule_id: str | None) -> bool:
    logs = get_today_logs_for_medication(medication_id)
    resolved_statuses = {"taken", "missed", "wrong_medication"}
    for log in logs:
        if log.get("status") not in resolved_statuses:
            continue
        if schedule_id is None:
            return True
        scheduled_at = str(log.get("scheduled_at", ""))
        schedule_res = (
            supabase.table("medication_schedules")
            .select("time_of_day")
            .eq("id", schedule_id)
            .limit(1)
            .execute()
        )
        if schedule_res.data:
            time_str = schedule_res.data[0].get("time_of_day", "")
            if time_str and time_str in scheduled_at:
                return True
    return False


def was_reminder_sent_today(medication_id: str, schedule_id: str) -> bool:
    logs = get_today_logs_for_medication(medication_id)
    for log in logs:
        if log.get("status") == "reminded" and schedule_id:
            scheduled_at = str(log.get("scheduled_at", ""))
            schedule_res = (
                supabase.table("medication_schedules")
                .select("time_of_day")
                .eq("id", schedule_id)
                .limit(1)
                .execute()
            )
            if schedule_res.data:
                time_str = schedule_res.data[0].get("time_of_day", "")
                if time_str and time_str in scheduled_at:
                    return True
    return False


def create_medication_log(
    medication_id: str,
    schedule_id: str | None,
    status: str,
    confirmation_method: str,
) -> dict[str, Any]:
    now = now_local().isoformat()
    payload = {
        "medication_id": medication_id,
        "scheduled_at": build_scheduled_at(schedule_id),
        "status": status,
        "confirmed_at": now if status in {"taken", "wrong_medication"} else None,
        "confirmation_method": confirmation_method,
    }
    return supabase.table("medication_logs").insert(payload).execute().data[0]


def record_reminder_sent(medication_id: str, schedule_id: str) -> None:
    if was_reminder_sent_today(medication_id, schedule_id):
        return
    create_medication_log(
        medication_id=medication_id,
        schedule_id=schedule_id,
        status="reminded",
        confirmation_method="scheduler",
    )


def get_medication_stats(elder_id: str) -> dict[str, Any]:
    meds_res = supabase.table("medications").select("id, name").eq("elder_id", elder_id).execute()
    if not meds_res.data:
        return {
            "total_logs": 0,
            "taken": 0,
            "missed": 0,
            "wrong": 0,
            "adherence_rate": 0,
            "recent_logs": [],
            "weekly_trend": [],
        }

    med_ids = [m["id"] for m in meds_res.data]
    med_names = {m["id"]: m["name"] for m in meds_res.data}

    logs_res = (
        supabase.table("medication_logs")
        .select("*")
        .in_("medication_id", med_ids)
        .order("scheduled_at", desc=False)
        .execute()
    )
    logs = logs_res.data or []

    actionable = [l for l in logs if l.get("status") in {"taken", "missed", "wrong_medication"}]
    taken = len([l for l in actionable if l.get("status") == "taken"])
    missed = len([l for l in actionable if l.get("status") == "missed"])
    wrong = len([l for l in actionable if l.get("status") == "wrong_medication"])
    total = len(actionable)
    rate = round((taken / total * 100), 2) if total > 0 else 0

    for log in logs:
        log["medication_name"] = med_names.get(log.get("medication_id"), "İlaç")

    weekly: dict[str, dict[str, int]] = {}
    for log in actionable:
        day = str(log.get("scheduled_at", ""))[:10]
        if not day:
            continue
        weekly.setdefault(day, {"taken": 0, "missed": 0, "wrong": 0})
        weekly[day][log["status"]] = weekly[day].get(log["status"], 0) + 1

    weekly_trend = [
        {"date": day, **counts}
        for day, counts in sorted(weekly.items())
    ][-7:]

    return {
        "total_logs": total,
        "taken": taken,
        "missed": missed,
        "wrong": wrong,
        "adherence_rate": rate,
        "recent_logs": logs[-10:],
        "weekly_trend": weekly_trend,
    }


def get_elder_alerts(elder_id: str, limit: int = 20) -> list[dict[str, Any]]:
    try:
        response = (
            supabase.table("alerts")
            .select("*")
            .eq("elder_id", elder_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return response.data or []
    except Exception as error:
        print(f"[ALERTS] Okuma hatası: {error}")
        return []


def get_elder_event_history(elder_id: str, limit: int = 30) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []

    meds_res = supabase.table("medications").select("id, name").eq("elder_id", elder_id).execute()
    med_names = {m["id"]: m["name"] for m in (meds_res.data or [])}
    med_ids = list(med_names.keys())

    if med_ids:
        logs_res = (
            supabase.table("medication_logs")
            .select("*")
            .in_("medication_id", med_ids)
            .order("scheduled_at", desc=True)
            .limit(limit)
            .execute()
        )
        status_labels = {
            "taken": ("Başarılı", "İlaç alındı"),
            "missed": ("Uyarı", "İlaç kaçırıldı"),
            "wrong_medication": ("Tehlike", "Yanlış ilaç gösterildi"),
            "snoozed": ("Bilgi", "Hatırlatma ertelendi"),
            "reminded": ("Bilgi", "Hatırlatma gönderildi"),
        }
        for log in logs_res.data or []:
            label, desc_prefix = status_labels.get(log.get("status"), ("Bilgi", log.get("status")))
            med_name = med_names.get(log.get("medication_id"), "İlaç")
            events.append(
                {
                    "timestamp": log.get("confirmed_at") or log.get("scheduled_at"),
                    "category": "İlaç Rutini",
                    "status": label,
                    "description": f"{desc_prefix}: {med_name}",
                }
            )

    for alert in get_elder_alerts(elder_id, limit=limit):
        events.append(
            {
                "timestamp": alert.get("created_at"),
                "category": "Eskalasyon",
                "status": "Tehlike" if alert.get("severity") == "high" else "Uyarı",
                "description": alert.get("description", ""),
            }
        )

    events.sort(key=lambda item: str(item.get("timestamp") or ""), reverse=True)
    return events[:limit]


def setup_kiosk_demo() -> dict[str, Any]:
    """Giriş yapmadan ilaç testi için sabit demo yaşlı + bugünkü ilaçları hazırlar."""
    existing = (
        supabase.table("elders")
        .select("*")
        .eq("full_name", DEMO_ELDER_NAME)
        .limit(1)
        .execute()
    )
    if existing.data:
        elder = existing.data[0]
    else:
        elder = (
            supabase.table("elders")
            .insert(
                {
                    "full_name": DEMO_ELDER_NAME,
                    "preferred_language": "tr",
                    "notes": f"users tablosu user_id: {DEMO_USER_ID}",
                    "city": "Test",
                }
            )
            .execute()
            .data[0]
        )

    elder_id = elder["id"]
    weekday = get_local_weekday()
    now = now_local()
    reminder_time = (now + timedelta(minutes=2)).strftime("%H:%M")
    current_time = now.strftime("%H:%M")

    existing_meds = list_medications(elder_id, today_only=False)
    existing_names = {med["name"] for med in existing_meds}

    for med in existing_meds:
        if med["name"] in {"Test Vitamin D", "Test Tansiyon İlacı"} and med.get("notes"):
            update_medication(med["id"], notes="")

    if "Test Vitamin D" not in existing_names:
        create_medication(
            elder_id=elder_id,
            name="Test Vitamin D",
            dosage="1 tablet",
            form="tablet",
            notes=None,
            schedules=[
                {"time_of_day": reminder_time, "days_of_week": [weekday]},
            ],
        )

    if "Test Tansiyon İlacı" not in existing_names:
        create_medication(
            elder_id=elder_id,
            name="Test Tansiyon İlacı",
            dosage="1 tablet",
            form="tablet",
            notes=None,
            schedules=[
                {"time_of_day": current_time, "days_of_week": [weekday]},
            ],
        )

    medications = list_medications(elder_id, today_only=True)
    return {
        "elder": elder,
        "demo_user_id": DEMO_USER_ID,
        "medications": medications,
        "reminder_in_minutes": 2,
        "message": (
            f"Demo hazır. {len(medications)} ilaç bugün için yüklendi. "
            f"Hatırlatma ~2 dk içinde gelebilir."
        ),
    }
