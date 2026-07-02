from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
from database import save_checkin, get_checkin_history

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