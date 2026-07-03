from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
from database import  supabase, save_checkin, get_checkin_history

router = APIRouter(tags=["Health & Medication"])

class CheckinModel(BaseModel):
    conversation_id: str  # Dinamik hale geldi
    mood: str

@router.post("/api/checkin")
async def daily_checkin(data: CheckinModel):
    try:
        print(f"[LOG] Ahmet Amca bugün kendini nasıl hissediyor -> {data.mood}")
        save_checkin(conversation_id=data.conversation_id, mood=data.mood)
        return {"status": "success"}
    except Exception as e:
        print(f"[HATA] Check-in kaydedilemedi: {str(e)}")
        raise HTTPException(status_code=500, detail="Check-in kaydedilemedi.")

@router.get("/api/checkin/history")
async def checkin_history(conversation_id: str, limit: int = 10):  # Query param olarak id alıyor
    try:
        history = get_checkin_history(conversation_id=conversation_id, limit=limit)
        return {"history": history}
    except Exception as e:
        print(f"[HATA] Check-in geçmişi alınamadı: {str(e)}")
        raise HTTPException(status_code=500, detail="Check-in geçmişi alınamadı.")



@router.get("/api/family/dashboard-summary/{conversation_id}")
async def get_family_dashboard_summary(conversation_id: str):
    try:
        # 1. En son check-in durumunu (Mood) çekiyoruz
        checkin_response = supabase.table("checkins") \
            .select("*") \
            .eq("conversation_id", conversation_id) \
            .order("created_at", desc=True) \
            .limit(1) \
            .execute()
        
        latest_mood = "Veri Yok"
        if checkin_response.data:
            latest_mood = checkin_response.data[0].get("mood", "Normal")

        # 2. Tüm geçmiş check-in loglarını tablo için çekiyoruz
        history_response = supabase.table("checkins") \
            .select("*") \
            .eq("conversation_id", conversation_id) \
            .order("created_at", desc=True) \
            .limit(10) \
            .execute()

        return {
            "success": True,
            "latest_mood": latest_mood,
            "medication_status": "%100 Alındı", # Gelecekte ilaç tablonuza bağlayacağız
            "activity_status": "Normal",
            "history": history_response.data
        }
    except Exception as e:
        print(f"[HATA] Dashboard verileri çekilemedi: {str(e)}")
        raise HTTPException(status_code=500, detail="Dashboard verileri yüklenemedi.")