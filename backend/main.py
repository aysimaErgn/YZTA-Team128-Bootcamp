from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from groq import Groq
import os
from dotenv import load_dotenv
import io
from datetime import datetime
import numpy as np
import cv2
from deepface import DeepFace  # dlib hatasını engelleyen güncel kütüphane
import json
import base64

# --- VERİTABANI FONKSİYONLARI ---
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

# --- PYDANTIC MODELLERİ (DİNAMİK ID DESTEKLİ) ---
class TextMessageModel(BaseModel):
    conversation_id: str  # Frontend'den gelecek olan dinamik ID
    message: str

class CheckinModel(BaseModel):
    conversation_id: str  # Sağlık durumu kontrolü de bu oturuma bağlanacak
    mood: str

class MedModel(BaseModel):
    med_id: str

class FaceAuthRequest(BaseModel):
    image_data: str 

# Yardımcı Fonksiyon: Base64'ü görüntüye çevirir
def base64_to_image(base64_string):
    try:
        if "," in base64_string:
            base64_string = base64_string.split(",")[1]
        img_bytes = base64.b64decode(base64_string)
        img_np = np.frombuffer(img_bytes, dtype=np.uint8)
        img = cv2.imdecode(img_np, cv2.IMREAD_COLOR)
        rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        return rgb_img
    except Exception as e:
        raise HTTPException(status_code=400, detail="Fotoğraf verisi işlenemedi.")

SYSTEM_PROMPT = (
    "Sen 'Yanımda Al' projesinde yalnız yaşayan yaşlılara destek olan sevecen, "
    "sabırlı ve neşeli bir dijital refakatçi ajansın. Karşındaki kişi 65 yaş üstü "
    "Ahmet Amca. Cümlelerin çok uzun olmasın, onun durumunu sor, empati yap ve "
    "onu motive et. Tıbbi teşhis veya tedavi önerisi verme."
)

# ==========================================
# 1. YAZILI SOHBET ENDPOINT (DİNAMİK)
# ==========================================
@app.post("/api/text-chat")
async def text_chat(data: TextMessageModel):
    try:
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
        
        # Gelen dinamik conversation_id ile veritabanına kaydediyoruz
        save_message(conversation_id=data.conversation_id, role="user", content=data.message)
        save_message(conversation_id=data.conversation_id, role="assistant", content=ai_response)
        
        return {"ai_response": ai_response}
    except Exception as e:
        return {"ai_response": f"SİSTEM HATASI BULUNDU: {str(e)}"}

# ==========================================
# 2. SESLİ SOHBET ENDPOINT (DİNAMİK)
# ==========================================
@app.post("/api/voice-chat")
async def voice_chat(
    file: UploadFile = File(...),
    conversation_id: str = Form(...)  # Frontend'den form-data içinde geliyor
):
    try:
        audio_bytes = await file.read()
        if not audio_bytes or len(audio_bytes) < 100:
            return {
                "user_transcription": "Ses algılanamadı.",
                "text": "Ses algılanamadı.",
                "ai_response": "Ahmet Amca, sesini tam alamadım. Tekrar söyler misin?",
                "response": "Ahmet Amca, sesini tam alamadım. Tekrar söyler misin?"
            }

        ext = os.path.splitext(file.filename)[1] if file.filename else ".wav"
        if not ext or ext == ".blob": ext = ".wav" 
            
        custom_filename = f"audio{ext}"
        audio_file_like = io.BytesIO(audio_bytes)

        transcription = groq_client.audio.transcriptions.create(
            file=(custom_filename, audio_file_like.read()), 
            model="whisper-large-v3",
            language="tr",
            response_format="json"
        )
        
        user_text = transcription.text

        if not user_text or user_text.strip() == "":
            user_text = "Sessizlik"
            ai_response = "Ahmet Amca, ne dediğini tam seçemedim. Tekrar söyler misin canım benim?"
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
            
            # Dinamik oturuma kaydetme
            save_message(conversation_id=conversation_id, role="user", content=user_text)
            save_message(conversation_id=conversation_id, role="assistant", content=ai_response)

    except Exception as e:
        user_text = "Ses dosyası işlenirken teknik hata oluştu."
        ai_response = "Ahmet Amca sesini tam alamadım, iyi misin, her şey yolunda mı?"
    
    return {
        "user_transcription": user_text,
        "text": user_text,
        "ai_response": ai_response,
        "response": ai_response,
        "message": ai_response
    }

# ==========================================
# 3. SOHBET LİSTESİNİ GETİR (GÜN GÜN AYIRIR)
# ==========================================
@app.get("/api/conversations")
async def get_conversations():
    try:
        response = supabase.table("messages").select("conversation_id, created_at").eq("role", "user").order("created_at", desc=True).execute()
        seen = set()
        unique_conversations = []
        for row in response.data:
            c_id = row["conversation_id"]
            if c_id not in seen:
                seen.add(c_id)
                try:
                    raw_date = row["created_at"].split("T")[0]
                    date_obj = datetime.strptime(raw_date, "%Y-%m-%d")
                    formatted_date = date_obj.strftime("%d.%m.%Y")
                except:
                    formatted_date = "Bilinmeyen Tarih"

                unique_conversations.append({
                    "conversation_id": c_id, 
                    "title": f"Sohbet - {formatted_date}"
                })
        return unique_conversations
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/conversations/{conversation_id}")
async def get_chat_history(conversation_id: str):
    try:
        response = supabase.table("messages").select("role", "content").eq("conversation_id", conversation_id).order("created_at", desc=False).execute()
        return response.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================
# 4. GÜNLÜK DURUM (CHECK-IN) ENDPOINTS
# ==========================================
@app.post("/api/checkin")
async def daily_checkin(data: CheckinModel):
    try:
        save_checkin(conversation_id=data.conversation_id, mood=data.mood)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Check-in kaydedilemedi.")

@app.get("/api/checkin/history")
async def checkin_history(conversation_id: str, limit: int = 10):
    try:
        history = get_checkin_history(conversation_id=conversation_id, limit=limit)
        return {"history": history}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Check-in geçmişi alınamadı.")

@app.post("/api/medication")
async def take_medication(data: MedModel):
    return {"status": "success"}

@app.post("/api/medication/recognize")
async def recognize_medication(file: UploadFile = File(...)):
    return {"status": "success", "recognized_med": "Vitamin Takviyesi"}

# ==========================================
# 5. YÜZ TANIMA SİSTEMİ (DEEPFACE ENTEGRELİ)
# ==========================================
@app.post("/api/auth/register-face")
async def register_face(request: FaceAuthRequest):
    try:
        rgb_image = base64_to_image(request.image_data)
        embeddings_data = DeepFace.represent(img_path=rgb_image, model_name="VGG-Face", enforce_detection=True, detector_backend="opencv")
        if not embeddings_data or len(embeddings_data) == 0:
            raise HTTPException(status_code=400, detail="Fotoğrafta yüz tespit edilemedi!")
            
        elderly_face_vector = embeddings_data[0]["embedding"]
        return {"success": True, "message": "Yüz imzası başarıyla çıkarıldı.", "face_vector": elderly_face_vector}
    except Exception as e:
        raise HTTPException(status_code=400, detail="Yüz analizi başarısız oldu.")

@app.post("/api/auth/face-login")
async def face_login(request: FaceAuthRequest):
    try:
        current_rgb_image = base64_to_image(request.image_data)
        current_embeddings = DeepFace.represent(img_path=current_rgb_image, model_name="VGG-Face", enforce_detection=True, detector_backend="opencv")
        if not current_embeddings or len(current_embeddings) == 0:
            raise HTTPException(status_code=400, detail="Yüz algılanamadı.")
            
        login_face_encoding = current_embeddings[0]["embedding"]
        users_response = supabase.table("users").select("id, name, face_vector").not_.is_("face_vector", "null").execute()
        
        for user in users_response.data:
            saved_face_vector = user["face_vector"]
            distance = DeepFace.verification.CosineDistance.calculate_distance(login_face_encoding, saved_face_vector)
            if distance <= 0.40:
                return {"success": True, "message": f"Giriş Başarılı. Hoş geldin {user['name']}", "user_id": user["id"]}
        raise HTTPException(status_code=401, detail="Yüz tanınamadı!")
    except Exception as e:
        raise HTTPException(status_code=400, detail="Giriş esnasında bir hata oluştu.")


# ==========================================
# 6. AİLE GİRİŞİ & GENEL KAYIT (EKLENENLER)
# ==========================================

class FamilyLoginModel(BaseModel):
    phone: str
    password: str

class FullRegisterModel(BaseModel):
    elderly: dict
    family: dict

@app.post("/api/auth/family-login")
async def family_login(data: FamilyLoginModel):
    try:
        # Supabase'den aile telefonuna göre kullanıcıyı arıyoruz
        response = supabase.table("users").select("*").eq("family_phone", data.phone).execute()
        
        if not response.data:
            raise HTTPException(status_code=404, detail="Bu telefon numarasına ait bir kayıt bulunamadı.")
            
        user = response.data[0]
        
        # Şifre kontrolü (Geliştirme aşaması için düz metin karşılaştırması)
        if user.get("family_password") != data.password:
            raise HTTPException(status_code=401, detail="Hatalı şifre girdiniz.")
            
        return {"success": True, "message": f"Hoş geldiniz, {user.get('family_name')}", "user_id": user.get("id")}
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail="Giriş yapılırken veritabanı hatası oluştu.")

@app.post("/api/auth/register")
async def register_user_and_family(data: FullRegisterModel):
    try:
        # Frontend'den (authorization.js) gelen iç içe nesneleri düzleştirip Supabase tablosuna uygun hale getiriyoruz
        flat_payload = {
            "name": data.elderly.get("name"),
            "age": data.elderly.get("age"),
            "face_vector": data.elderly.get("face_vector"),  # DeepFace'den gelen 4096 boyutlu array
            "family_name": data.family.get("name"),
            "family_phone": data.family.get("phone"),
            "family_password": data.family.get("password")
        }
        
        # Supabase 'users' tablonuza tek satır olarak ekleme yapıyoruz
        response = supabase.table("users").insert(flat_payload).execute()
        return {"success": True, "message": "Kayıt işlemi başarıyla tamamlandı!"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Veritabanı kayıt hatası: {str(e)}")



if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)