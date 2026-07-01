from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from groq import Groq
import os
from dotenv import load_dotenv
import io
from datetime import datetime

# --- SENİN YAZDIĞIN VERİTABANI DOSYASINI İÇERİ AKTARIYORUZ ---
from database import save_message, create_client, Client, save_checkin, get_checkin_history

app = FastAPI(title="Yanımda Al - Yaşlı Refakatçi API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

load_dotenv()
groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))


SUPABASE_URL  = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

class TextChatRequest(BaseModel):
    conversation_id: str
    message: str

# Pydantic Modelleri
class CheckinModel(BaseModel):
    mood: str

class MedModel(BaseModel):
    med_id: str

# YAZILI SOHBET İÇİN MODEL
class TextMessageModel(BaseModel):
    message: str

# SYSTEM PROMPT (Yapay zekanın bürüneceği ortak kişilik)
SYSTEM_PROMPT = (
    "Sen 'Yanımda Al' projesinde yalnız yaşayan yaşlılara destek olan sevecen, "
    "sabırlı and neşeli bir dijital refakatçi ajansın. Karşındaki kişi 65 yaş üstü "
    "Ahmet Amca. Cümlelerin çok uzun olmasın, onun durumunu sor, empati yap ve "
    "onu motive et. Tıbbi teşhis veya tedavi önerisi verme."
)

# =====================================================================
# GÜNCEL: Supabase 'conversations' tablosundan aldığın gerçek UUID bağlandı!
# =====================================================================
GECERLI_UUID = "890f8eb3-2734-47d8-864a-df1a33f9a161"


# ==========================================
# GÜNCEL: YAZILI SOHBET ENDPOINT
# ==========================================
@app.post("/api/text-chat")
async def text_chat(data: TextMessageModel):
    try:
        # LOG print(f"\n>>>>>> YENİ MESAJ GELDİ: {data.message} <<<<<<\n")
        
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": data.message}
            ],
            max_tokens=150,
            temperature=0.7
        )
        ai_response = response.choices[0].message.content
        
        # --- VERİTABANINA KAYIT (YAZILI SOHBET) ---
        save_message(conversation_id=GECERLI_UUID, role="user", content=data.message)
        save_message(conversation_id=GECERLI_UUID, role="assistant", content=ai_response)
        
        return {"ai_response": ai_response}
        
    except Exception as e:
        gizli_hata = f"SİSTEM HATASI BULUNDU: {str(e)}"
        print(gizli_hata)
        return {"ai_response": gizli_hata}


# ==========================================
# SESLİ SOHBET ENDPOINT (SABİT SİMÜLASYON)
# ==========================================
@app.post("/api/voice-chat")
async def voice_chat(file: UploadFile = File(...)):
    try:
        audio_bytes = await file.read()
        
        if not audio_bytes or len(audio_bytes) < 100:
            print(f"[UYARI] Ahmet Amca'dan boş ses dosyası geldi.")
            return {
                "user_transcription": "Ses algılanamadı.",
                "text": "Ses algılanamadı.",
                "ai_response": "Ahmet Amca, sesin geldi ama ahizeye tam üfleyemedin galiba, sesini duyamadım. Tekrar söyler misin?",
                "response": "Ahmet Amca, sesin geldi ama ahizeye tam üfleyemedin galiba, sesini duyamadım. Tekrar söyler misin?"
            }

        ext = os.path.splitext(file.filename)[1] if file.filename else ".wav"
        if not ext or ext == ".blob":
            ext = ".wav" 
            
        custom_filename = f"audio{ext}"
        audio_file_like = io.BytesIO(audio_bytes)

        transcription = groq_client.audio.transcriptions.create(
            file=(custom_filename, audio_file_like.read()), 
            model="whisper-large-v3",
            language="tr",
            response_format="json"
        )
        
        user_text = transcription.text
        print(f"[SES ANLAŞILDI] Ahmet Amca: {user_text}")

        if not user_text or user_text.strip() == "":
            user_text = "Sessizlik"
            ai_response = "Ahmet Amca, sesin geldi ama ne dediğini tam seçemedim. Tekrar söyler misin canım benim?"
        else:
            response = groq_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_text}
                ],
                max_tokens=150,
                temperature=0.7
            )
            ai_response = response.choices[0].message.content
            
            # --- VERİTABANINA KAYIT (SESLİ SOHBET) ---
            save_message(conversation_id=GECERLI_UUID, role="user", content=user_text)
            save_message(conversation_id=GECERLI_UUID, role="assistant", content=ai_response)

    except Exception as e:
        gizli_hata = f"[KRİTİK HATA] Ses işlenirken bir sorun oluştu: {str(e)}"
        print(gizli_hata)
        user_text = "Ses dosyası işlenirken teknik hata oluştu."
        ai_response = "Ahmet Amca sesini tam alamadım, hattım kesildi galiba. İyi misin, her şey yolunda mı?"
    
    return {
        "user_transcription": user_text,
        "text": user_text,
        "ai_response": ai_response,
        "response": ai_response,
        "message": ai_response
    }

@app.get("/api/conversations")
async def get_conversations():
    try:
        # Bu sefer content yerine created_at bilgisini çekiyoruz
        response = supabase.table("messages").select("conversation_id, created_at").eq("role", "user").order("created_at", desc=True).execute()
        
        seen = set()
        unique_conversations = []
        for row in response.data:
            c_id = row["conversation_id"]
            if c_id not in seen:
                seen.add(c_id)
                
                # Supabase'den gelen tarihi (2026-07-01T11:53:41...) parçalayıp okunabilir formata getiriyoruz
                try:
                    raw_date = row["created_at"].split("T")[0] # "2026-07-01" alır
                    date_obj = datetime.strptime(raw_date, "%Y-%m-%d")
                    formatted_date = date_obj.strftime("%d.%m.%Y") # "01.07.2026" yapar
                except:
                    formatted_date = "Bilinmeyen Tarih"

                unique_conversations.append({
                    "conversation_id": c_id, 
                    "title": formatted_date # Artık başlık olarak tarih gidiyor
                })
        
        return unique_conversations
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 2. SEÇİLEN SOHBETİN DETAYINI GETİR
@app.get("/api/conversations/{conversation_id}")
async def get_chat_history(conversation_id: str):
    try:
        response = supabase.table("messages").select("role", "content").eq("conversation_id", conversation_id).order("created_at", desc=False).execute()
        return response.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/checkin")
async def daily_checkin(data: CheckinModel):
    try:
        print(f"[LOG] Ahmet Amca bugün kendini nasıl hissediyor -> {data.mood}")
        save_checkin(conversation_id=GECERLI_UUID, mood=data.mood)
        return {"status": "success"}
    except Exception as e:
        print(f"[HATA] Check-in kaydedilemedi: {str(e)}")
        raise HTTPException(status_code=500, detail="Check-in kaydedilemedi.")

@app.get("/api/checkin/history")
async def checkin_history(limit: int = 10):
    try:
        history = get_checkin_history(conversation_id=GECERLI_UUID, limit=limit)
        return {"history": history}
    except Exception as e:
        print(f"[HATA] Check-in geçmişi alınamadı: {str(e)}")
        raise HTTPException(status_code=500, detail="Check-in geçmişi alınamadı.")

@app.post("/api/medication")
async def take_medication(data: MedModel):
    print(f"[LOG] İlaç alımı onaylandı -> {data.med_id}")
    return {"status": "success"}

@app.post("/api/medication/recognize")
async def recognize_medication(file: UploadFile = File(...)):
    return {"status": "success", "recognized_med": "Vitamin Takviyesi"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)