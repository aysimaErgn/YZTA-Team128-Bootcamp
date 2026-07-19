from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from groq import Groq
import os
from dotenv import load_dotenv
load_dotenv()
import io
from datetime import datetime
import numpy as np
import cv2

def _get_deepface():
    try:
        from deepface import DeepFace
        return DeepFace
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail="Yüz tanıma modülü hazır değil. 'pip install deepface tf-keras==2.18.0' komutunu çalıştırın.",
        ) from error

import json
import base64
import asyncio

from database import save_message, create_client, Client, save_checkin, get_checkin_history, get_today_checkin_status
from medication.router import router as medication_router
from medication.crud_router import router as medication_crud_router
from routers.websocket import router as websocket_router
from routers.health import router as health_router
from medication.scheduler import start_scheduler, set_event_loop

app = FastAPI(title="Yanımda Al - Yaşlı Refakatçi API")

@app.on_event("startup")
async def startup_event():
    set_event_loop(asyncio.get_running_loop())
    start_scheduler()

def _cors_origins() -> list[str]:
    raw = (os.getenv("CORS_ORIGINS") or "*").strip()
    if raw == "*":
        return ["*"]
    return [origin.strip() for origin in raw.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(medication_router)
app.include_router(medication_crud_router)
app.include_router(websocket_router)
app.include_router(health_router)

groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

SUPABASE_URL  = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- PYDANTIC MODELLERİ (DİNAMİK ID DESTEKLİ) ---
class TextMessageModel(BaseModel):
    conversation_id: str  # Frontend'den gelecek olan dinamik ID
    message: str
    user_id: str | None = None    # Bu mesajın hangi kayıtlı kullanıcıya ait olduğu
    user_name: str | None = None  # AI'ın kişiye doğru isimle hitap edebilmesi için

class CheckinModel(BaseModel):
    conversation_id: str  # Sağlık durumu kontrolü de bu oturuma bağlanacak
    mood: str

class MedModel(BaseModel):
    med_id: str

class SummaryRequestModel(BaseModel):
    conversation_id: str

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

def build_system_prompt(user_name: str | None = None):
    display_name = user_name or "karşındaki kişi"
    return (
        "Sen 'Yanımda Al' projesinde yalnız yaşayan yaşlılara destek olan sevecen, "
        f"sabırlı ve neşeli bir dijital refakatçi ajansın. Karşındaki kişi 65 yaş üstü "
        f"{display_name}. Cümlelerin çok uzun olmasın, onun durumunu sor, empati yap ve "
        "onu motive et. Tıbbi teşhis veya tedavi önerisi verme."
    )


def _legacy_text_reply(message: str, user_name: str | None = None) -> str:
    response = groq_client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": build_system_prompt(user_name)},
            {"role": "user", "content": message},
        ],
        max_tokens=150,
        temperature=0.7,
    )
    return response.choices[0].message.content


def _resolve_elder_id_for_chat(user_id: str | None, user_name: str | None) -> str | None:
    if not user_id and not (user_name or "").strip():
        return None
    try:
        from medication import service as medication_service

        elder = medication_service.resolve_elder_for_user(
            user_id or "guest",
            (user_name or "Yakınız").strip(),
        )
        return elder.get("id")
    except Exception as error:
        print(f"[ORCHESTRATOR] elder_id çözülemedi: {error}")
        return user_id


# ==========================================
# 1. YAZILI SOHBET ENDPOINT (DİNAMİK)
# ==========================================
@app.post("/api/text-chat")
async def text_chat(data: TextMessageModel):
    try:
        from orchestrator.graph import is_orchestrator_enabled, run_orchestrator

        if is_orchestrator_enabled():
            elder_id = _resolve_elder_id_for_chat(data.user_id, data.user_name)
            result = run_orchestrator(
                message=data.message,
                conversation_id=data.conversation_id,
                elder_id=elder_id,
                user_name=data.user_name,
                user_id=data.user_id,
            )
            ai_response = result["ai_response"]
            save_message(
                conversation_id=data.conversation_id,
                role="user",
                content=data.message,
                user_id=data.user_id,
                elder_id=elder_id,
            )
            save_message(
                conversation_id=data.conversation_id,
                role="assistant",
                content=ai_response,
                user_id=data.user_id,
                elder_id=elder_id,
            )
            return {
                "ai_response": ai_response,
                "intent": result.get("intent"),
                "routed_agent": result.get("routed_agent"),
                "escalation": result.get("escalation", False),
                "urgency": result.get("urgency"),
                "detected_mood": result.get("detected_mood"),
                "shared_health_context": result.get("shared_health_context") or {},
            }

        ai_response = _legacy_text_reply(data.message, data.user_name)
        save_message(conversation_id=data.conversation_id, role="user", content=data.message, user_id=data.user_id)
        save_message(conversation_id=data.conversation_id, role="assistant", content=ai_response, user_id=data.user_id)
        return {"ai_response": ai_response}
    except Exception as e:
        return {"ai_response": f"SİSTEM HATASI BULUNDU: {str(e)}"}

# ==========================================
# 2. SESLİ SOHBET ENDPOINT (DİNAMİK)
# ==========================================
@app.post("/api/voice-chat")
async def voice_chat(
    file: UploadFile = File(...),
    conversation_id: str = Form(...),  # Frontend'den form-data içinde geliyor
    user_id: str = Form(None),
    user_name: str = Form(None)
):
    display_name = user_name or "canım"
    try:
        audio_bytes = await file.read()
        if not audio_bytes or len(audio_bytes) < 100:
            return {
                "user_transcription": "Ses algılanamadı.",
                "text": "Ses algılanamadı.",
                "ai_response": f"{display_name}, sesini tam alamadım. Tekrar söyler misin?",
                "response": f"{display_name}, sesini tam alamadım. Tekrar söyler misin?"
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
            ai_response = f"{display_name}, ne dediğini tam seçemedim. Tekrar söyler misin?"
            return {
                "user_transcription": user_text,
                "text": user_text,
                "ai_response": ai_response,
                "response": ai_response,
                "message": ai_response,
            }

        from orchestrator.graph import is_orchestrator_enabled, run_orchestrator

        if is_orchestrator_enabled():
            elder_id = _resolve_elder_id_for_chat(user_id, user_name)
            result = run_orchestrator(
                message=user_text,
                conversation_id=conversation_id,
                elder_id=elder_id,
                user_name=user_name,
                user_id=user_id,
            )
            ai_response = result["ai_response"]
            save_message(conversation_id=conversation_id, role="user", content=user_text, user_id=user_id)
            save_message(conversation_id=conversation_id, role="assistant", content=ai_response, user_id=user_id)
            return {
                "user_transcription": user_text,
                "text": user_text,
                "ai_response": ai_response,
                "response": ai_response,
                "message": ai_response,
                "intent": result.get("intent"),
                "routed_agent": result.get("routed_agent"),
                "escalation": result.get("escalation", False),
                "urgency": result.get("urgency"),
                "detected_mood": result.get("detected_mood"),
                "shared_health_context": result.get("shared_health_context") or {},
            }

        ai_response = _legacy_text_reply(user_text, user_name)
        save_message(conversation_id=conversation_id, role="user", content=user_text, user_id=user_id)
        save_message(conversation_id=conversation_id, role="assistant", content=ai_response, user_id=user_id)

    except Exception as e:
        user_text = "Ses dosyası işlenirken teknik hata oluştu."
        ai_response = f"{display_name}, sesini tam alamadım, iyi misin, her şey yolunda mı?"
    
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

@app.get("/api/checkin/status")
async def checkin_status(conversation_id: str):
    """
    Check-in eksikliği tespiti: Bugün bu kullanıcı için check-in yapılmış mı?
    Aile tarafı ve Durumum ekranı bu bilgiyi kullanarak uyarı gösterebilir.
    """
    try:
        today_checkin = get_today_checkin_status(conversation_id=conversation_id)
        return {
            "checked_in_today": today_checkin is not None,
            "last_checkin": today_checkin
        }
    except Exception as e:
        print("!!! CHECKIN-STATUS HATASI:", str(e))
        raise HTTPException(status_code=500, detail="Check-in durumu alınamadı.")

@app.post("/api/medication")
async def take_medication(data: MedModel):
    return {"status": "success"}

# İlaç tanıma: backend/medication/router.py

@app.post("/api/family/generate-ai-summary")
async def generate_ai_summary(data: SummaryRequestModel):
    try:
        messages_response = (
            supabase.table("messages")
            .select("role, content")
            .eq("conversation_id", data.conversation_id)
            .order("created_at", desc=True)
            .limit(15)
            .execute()
        )

        if not messages_response.data:
            return {
                "success": True,
                "summary": (
                    "Bugün henüz dijital refakatçi ile bir sohbet gerçekleşmedi. "
                    "Yaşlınızın genel durumu stabil görünüyor."
                ),
            }

        chat_history = list(reversed(messages_response.data))
        formatted_history = ""
        for msg in chat_history:
            sender = "Yaşlı" if msg["role"] == "user" else "Asistan"
            formatted_history += f"{sender}: {msg['content']}\n"

        ai_family_prompt = (
            "Sen 'Yanımda Al' projesinin arka plandaki analiz zekasısın. "
            "Sana yalnız yaşayan bir birey ile dijital refakatçi asistan arasındaki son sohbet geçmişi verilecek. "
            "Bu konuşmaları analiz ederek aileye/refakatçiye ulaştırılacak kısa, samimi ama bilgilendirici bir günlük özet çıkar. "
            "Mod, sağlık veya ilaçlarla ilgili ipuçlarını ve varsa sıkıntıları belirt. "
            "Tıbbi kararlar verme. Maksimum 3-4 cümle olsun."
        )

        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": ai_family_prompt},
                {"role": "user", "content": f"Analiz edilecek sohbet geçmişi:\n{formatted_history}"},
            ],
            max_tokens=200,
            temperature=0.5,
        )

        return {"success": True, "summary": response.choices[0].message.content.strip()}
    except Exception as error:
        print(f"[AI ÖZET HATASI]: {error}")
        raise HTTPException(status_code=500, detail="Yapay zeka özeti şu an üretilemedi.") from error

# ==========================================
# 5. YÜZ TANIMA SİSTEMİ (DEEPFACE ENTEGRELİ)
# ==========================================
@app.post("/api/auth/register-face")
async def register_face(request: FaceAuthRequest):
    try:
        rgb_image = base64_to_image(request.image_data)
        DeepFace = _get_deepface()
        embeddings_data = DeepFace.represent(img_path=rgb_image, model_name="VGG-Face", enforce_detection=False, detector_backend="skip")
        if not embeddings_data or len(embeddings_data) == 0:
            raise HTTPException(status_code=400, detail="Fotoğrafta yüz tespit edilemedi!")
            
        elderly_face_vector = embeddings_data[0]["embedding"]
        return {"success": True, "message": "Yüz imzası başarıyla çıkarıldı.", "face_vector": elderly_face_vector}
    except Exception as e:
        print("!!! REGISTER-FACE HATASI:", str(e))
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=400, detail="Yüz analizi başarısız oldu.")

@app.post("/api/auth/face-login")
async def face_login(request: FaceAuthRequest):
    try:
        current_rgb_image = base64_to_image(request.image_data)
        DeepFace = _get_deepface()
        current_embeddings = DeepFace.represent(img_path=current_rgb_image, model_name="VGG-Face", enforce_detection=False, detector_backend="skip")
        if not current_embeddings or len(current_embeddings) == 0:
            raise HTTPException(status_code=400, detail="Yüz algılanamadı.")
            
        login_face_encoding = current_embeddings[0]["embedding"]
        users_response = supabase.table("users").select("id, name, face_vector").not_.is_("face_vector", "null").execute()
        
        for user in users_response.data:
            saved_face_vector = user["face_vector"]
            if not saved_face_vector or len(saved_face_vector) != len(login_face_encoding):
                continue
            distance = DeepFace.verification.find_cosine_distance(login_face_encoding, saved_face_vector)
            print(f"-> {user['name']} için ölçülen mesafe: {distance}")
            if distance <= 0.68:
                return {"success": True, "message": f"Giriş Başarılı. Hoş geldin {user['name']}", "user_id": user["id"], "name": user["name"]}
        raise HTTPException(status_code=401, detail="Yüz tanınamadı!")
    except Exception as e:
        print("!!! FACE-LOGIN HATASI:", str(e))
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

        # Frontend (authorization.js) tam olarak bu alan adlarını okuyor:
        # family_name, elderly_id, elderly_name -> bunlar eksikti, elderly_id "undefined" geliyordu.
        return {
            "success": True,
            "message": f"Hoş geldiniz, {user.get('family_name')}",
            "family_name": user.get("family_name"),
            "elderly_id": user.get("id"),
            "elderly_name": user.get("name"),
            "user_id": user.get("id")  # geriye dönük uyumluluk için bırakıldı
        }
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail="Giriş yapılırken veritabanı hatası oluştu.")

# ==========================================
# 6.b AİLE PANELİ - ÖZET VERİLERİ (EKSİK OLAN VE EKLENEN)
# ==========================================
class SummaryRequestModel(BaseModel):
    conversation_id: str

@app.get("/api/family/dashboard-summary/{elderly_id}")
async def dashboard_summary(elderly_id: str):
    """
    dashboard.js bu endpoint'i çağırıyordu ama main.py'de hiç tanımlı değildi (404 sebebi buydu).
    Not: Şu an veritabanı şemasında ilaç uyumu (medication) ve aktivite (activity) için
    kalıcı bir kayıt mekanizması yok (/api/medication endpoint'i hiçbir şeyi veritabanına yazmıyor).
    Bu yüzden o iki alanı gerçek veri gelene kadar dürüstçe "Takip edilmiyor" olarak dönüyoruz;
    sadece check-in (mood) verisi gerçek veritabanından geliyor.
    """
    try:
        checkin = get_today_checkin_status(conversation_id=elderly_id)
        latest_mood = checkin["mood"] if checkin else "normal"

        return {
            "success": True,
            "latest_mood": latest_mood,
            "medication_status": "Takip edilmiyor",
            "activity_status": "Takip edilmiyor"
        }
    except Exception as e:
        print("!!! DASHBOARD-SUMMARY HATASI:", str(e))
        raise HTTPException(status_code=500, detail="Panel özeti alınamadı.")


@app.post("/api/family/generate-ai-summary")
async def generate_ai_summary(data: SummaryRequestModel):
    """dashboard.js bu endpoint'i de çağırıyordu ama main.py'de tanımlı değildi (404 sebebi buydu)."""
    try:
        # ÖNEMLİ: Sohbet mesajları elderly_id (users.id) ile değil, sayfa her açıldığında
        # rastgele üretilen bir "activeChatId" (conversation_id) ile kaydediliyor (bkz. app.js).
        # Bu yüzden conversation_id üzerinden arama yapmak mesajları hiç bulamıyordu.
        # Mesajlar gönderilirken gerçek kullanıcı kimliği ayrıca "user_id" sütununa da yazılıyor
        # (app.js -> realUserId), o yüzden burada asıl aramayı user_id üzerinden yapıyoruz.
        #
        # Ayrıca bu "günlük özet" olduğu için sadece BUGÜNÜN mesajlarını çekiyoruz.
        # Öncesinde tarih filtresi yoktu, bu yüzden dünkü/önceki günlerin mesajları da
        # son-15 mesaj limitine dahil olup özete karışabiliyordu.
        today_start = datetime.now().strftime("%Y-%m-%dT00:00:00")

        messages_response = supabase.table("messages") \
            .select("role, content") \
            .eq("user_id", data.conversation_id) \
            .gte("created_at", today_start) \
            .order("created_at", desc=True) \
            .limit(30) \
            .execute()

        if not messages_response.data:
            return {
                "success": True,
                "summary": "Bugün henüz dijital refakatçi ile bir sohbet gerçekleşmedi. Yaşlınızın genel durumu stabil görünüyor."
            }

        chat_history = list(reversed(messages_response.data))

        # İlgili yaşlının gerçek adını çekiyoruz (sabit isim kullanmıyoruz)
        elderly_name = "kullanıcı"
        try:
            user_resp = supabase.table("users").select("name").eq("id", data.conversation_id).execute()
            if user_resp.data and user_resp.data[0].get("name"):
                elderly_name = user_resp.data[0]["name"]
        except Exception as name_err:
            print("[İSİM ÇEKME HATASI]:", str(name_err))

        formatted_history = ""
        for msg in chat_history:
            sender = elderly_name if msg["role"] == "user" else "Asistan"
            formatted_history += f"{sender}: {msg['content']}\n"

        ai_family_prompt = (
            "Sen 'Yanımda Al' projesinin arka plandaki analiz zekasısın. "
            f"Sana yalnız yaşayan {elderly_name} ile dijital refakatçi asistan arasındaki son sohbet geçmişi verilecek. "
            f"Bu konuşmaları analiz ederek {elderly_name}'nın ailesine/refakatçisine ulaştırılacak kısa, "
            f"samimi ama bilgilendirici bir günlük özet çıkar. {elderly_name}'nın modunu, sağlığıyla veya "
            "ilaçlarıyla ilgili verdiği ipuçlarını, eğer varsa bir sıkıntısını veya talebini mutlaka belirt. "
            "Tıbbi kararlar verme, doğrudan durumu özetle. Maksimum 3-4 cümle olsun."
        )

        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": ai_family_prompt},
                {"role": "user", "content": f"Analiz edilecek sohbet geçmişi:\n{formatted_history}"}
            ],
            max_tokens=200,
            temperature=0.5
        )

        ai_summary = response.choices[0].message.content.strip()
        return {"success": True, "summary": ai_summary}

    except Exception as e:
        print(f"[AI ÖZET HATASI]: {str(e)}")
        raise HTTPException(status_code=500, detail="Yapay zeka özeti şu an üretilemedi.")


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


# ==========================================
# 7. YAŞLI İÇİN AD+YAŞ İLE GİRİŞ (B PLANI)
# ==========================================
class CredentialsAuthRequest(BaseModel):
    name: str
    age: int

@app.post("/api/auth/credentials-login")
async def credentials_login(request: CredentialsAuthRequest):
    try:
        response = supabase.table("users").select("id", "name", "age").execute()
        user_data = response.data

        if not user_data:
            raise HTTPException(status_code=401, detail="Sistemde kayıtlı hiçbir kullanıcı yok.")

        matched_user = None
        for user in user_data:
            db_name = str(user.get("name")).strip().lower().replace("I", "ı").replace("İ", "i")
            input_name = str(request.name).strip().lower().replace("I", "ı").replace("İ", "i")

            if db_name == input_name and int(user.get("age")) == int(request.age):
                matched_user = user
                break

        if matched_user:
            return {
                "success": True,
                "message": f"Giriş Başarılı. Hoş geldin {matched_user['name']}",
                "user_id": matched_user["id"],
                "name": matched_user["name"]
            }
        else:
            raise HTTPException(status_code=401, detail="Girdiğiniz ad veya yaş hatalı.")

    except Exception as e:
        print("!!! CREDENTIALS-LOGIN HATASI:", str(e))
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=400, detail=f"Giriş esnasında hata: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)