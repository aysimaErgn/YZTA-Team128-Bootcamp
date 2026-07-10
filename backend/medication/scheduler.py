import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler

from database import supabase
from medication import service as medication_service
from routers.websocket import manager

LOCAL_TZ = ZoneInfo("Europe/Istanbul")
_main_loop: asyncio.AbstractEventLoop | None = None
_sent_reminders: set[str] = set()


def set_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _main_loop
    _main_loop = loop


def _reminder_key(schedule_id: str, date_str: str) -> str:
    return f"{schedule_id}:{date_str}"


def _dispatch_ws_message(payload: dict, elder_id: str) -> None:
    if not _main_loop or not _main_loop.is_running():
        print(f"[SCHEDULER] Event loop yok, WS mesajı gönderilemedi: {elder_id}")
        return
    asyncio.run_coroutine_threadsafe(
        manager.send_personal_message(payload, elder_id),
        _main_loop,
    )


def check_medications() -> None:
    """Her dakika: zamanı gelen ilaçları bulur, çift gönderimi engeller, WS ile uyarır."""
    try:
        now = datetime.now(LOCAL_TZ)
        current_time_str = now.strftime("%H:%M")
        current_day_of_week = now.isoweekday()
        today_str = now.strftime("%Y-%m-%d")

        response = (
            supabase.table("medication_schedules")
            .select("*, medications(*)")
            .execute()
        )
        if not response.data:
            return

        for schedule in response.data:
            sched_time = schedule.get("time_of_day")
            if not sched_time or not sched_time.startswith(current_time_str):
                continue

            days = schedule.get("days_of_week") or []
            if current_day_of_week not in days:
                continue

            medication = schedule.get("medications")
            if not medication or not medication.get("is_active", True):
                continue

            med_id = medication.get("id")
            schedule_id = schedule.get("id")
            elder_id = medication.get("elder_id")
            med_name = medication.get("name")
            dosage = medication.get("dosage", "")

            if not elder_id or not med_name or not med_id or not schedule_id:
                continue

            if medication_service.has_schedule_been_resolved_today(med_id, schedule_id):
                continue

            reminder_key = _reminder_key(schedule_id, today_str)
            if reminder_key in _sent_reminders:
                continue

            payload = {
                "aksiyon": "ILAC_HATIRLATMA",
                "medication_id": med_id,
                "schedule_id": schedule_id,
                "ilac_adi": med_name,
                "dozaj": dosage,
            }
            _dispatch_ws_message(payload, elder_id)
            medication_service.record_reminder_sent(med_id, schedule_id)
            _sent_reminders.add(reminder_key)
            print(f"[SCHEDULER] Hatırlatma gönderildi: {med_name} → {elder_id}")

    except Exception as error:
        print(f"[SCHEDULER] Hata: {error}")


def check_escalations() -> None:
    """30 dakika geçmiş, hâlâ alınmamış dozları eskalasyon olarak işaretler."""
    try:
        now = datetime.now(LOCAL_TZ)
        thirty_mins_ago = now - timedelta(minutes=30)
        target_time_str = thirty_mins_ago.strftime("%H:%M")
        current_day_of_week = thirty_mins_ago.isoweekday()

        response = (
            supabase.table("medication_schedules")
            .select("*, medications(*)")
            .execute()
        )
        if not response.data:
            return

        for schedule in response.data:
            sched_time = schedule.get("time_of_day")
            if not sched_time or not sched_time.startswith(target_time_str):
                continue

            days = schedule.get("days_of_week") or []
            if current_day_of_week not in days:
                continue

            medication = schedule.get("medications")
            if not medication or not medication.get("is_active", True):
                continue

            med_id = medication.get("id")
            schedule_id = schedule.get("id")
            if not med_id or not schedule_id:
                continue

            if medication_service.has_schedule_been_resolved_today(med_id, schedule_id):
                continue

            from medication.health_agent import record_missed

            result = record_missed(med_id, schedule_id, reason="system_timeout")
            if result.get("decision") == "missed":
                med_name = medication.get("name", "İlaç")
                elder_id = medication.get("elder_id")
                print(f"[ESKALASYON] {elder_id} — '{med_name}' 30 dk içinde alınmadı.")

    except Exception as error:
        print(f"[ESKALASYON] Hata: {error}")


def start_scheduler() -> None:
    scheduler = BackgroundScheduler(timezone=str(LOCAL_TZ))
    scheduler.add_job(check_medications, "interval", minutes=1, id="med_check")
    scheduler.add_job(check_escalations, "interval", minutes=1, id="med_escalation")
    scheduler.start()
    print("[SCHEDULER] Başlatıldı (Europe/Istanbul). İlaç hatırlatma + eskalasyon aktif.")
