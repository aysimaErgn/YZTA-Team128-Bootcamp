from fastapi import APIRouter, HTTPException

from database import supabase
from medication import service as medication_service

router = APIRouter(tags=["Family Dashboard"])


@router.get("/api/family/dashboard-summary/{conversation_id}")
async def get_family_dashboard_summary(conversation_id: str):
    try:
        checkin_response = (
            supabase.table("checkins")
            .select("*")
            .eq("conversation_id", conversation_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

        latest_mood = "Veri Yok"
        if checkin_response.data:
            latest_mood = checkin_response.data[0].get("mood", "Normal")

        history_response = (
            supabase.table("checkins")
            .select("*")
            .eq("conversation_id", conversation_id)
            .order("created_at", desc=True)
            .limit(10)
            .execute()
        )

        elder = medication_service.resolve_elder_for_user(conversation_id, "Yakınız")
        elder_id = elder.get("id")
        med_stats = medication_service.get_medication_stats(elder_id) if elder_id else {}
        adherence = med_stats.get("adherence_rate", 0)
        total = med_stats.get("total_logs", 0)

        medication_status = f"%{adherence} Uyum" if total > 0 else "Henüz kayıt yok"
        recent_alerts = medication_service.get_elder_alerts(elder_id, limit=5) if elder_id else []

        return {
            "success": True,
            "latest_mood": latest_mood,
            "medication_status": medication_status,
            "medication_stats": med_stats,
            "recent_alerts": recent_alerts,
            "activity_status": "Normal",
            "history": history_response.data,
        }
    except Exception as error:
        print(f"[HATA] Dashboard verileri çekilemedi: {error}")
        raise HTTPException(status_code=500, detail="Dashboard verileri yüklenemedi.") from error
