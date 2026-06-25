from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from groq import Groq
import os
from dotenv import load_dotenv
import io

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
    "sabırlı ve neşeli bir dijital refakatçi ajansın. Karşındaki kişi 65 yaş üstü "
    "Ahmet Amca. Cümlelerin çok uzun olmasın, onun durumunu sor, empati yap ve "
    "onu motive et. Tıbbi teşhis veya tedavi önerisi verme."
)


# ==========================================
# GÜNCEL: YAZILI SOHBET ENDPOINT
# ==========================================
@app.post("/api/text-chat")
async def text_chat(data: TextMessageModel):
    """
    Ahmet Amca klavyeden yazıp gönderdiğinde doğrudan burası tetiklenir.
    """
    try:
        # MODEL GÜNCELLENDİ: "llama-3.1-8b-instant" yapıldı
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
    except Exception as e:
        print(f"[HATA] {e}")
        ai_response = "Ahmet Amca yazdıklarını okudum ama sistemimde ufak bir sorun oldu. İyi misin, her şey yolunda mı?"

    return {"ai_response": ai_response}


# ==========================================
# SESLİ SOHBET ENDPOINT (SABİT SİMÜLASYON)
# ==========================================
@app.post("/api/voice-chat")
async def voice_chat(file: UploadFile = File(...)):
    """
    Windows dosya izin hatalarını ve boş dosya sorunlarını önlemek için 
    sesi diske yazmadan doğrudan hafıza (BytesIO) üzerinden Whisper'a gönderir.
    """
    try:
        # Gelen ses verisini oku
        audio_bytes = await file.read()
        
        # 1. Boş dosya kontrolü
        if not audio_bytes or len(audio_bytes) < 100:
            print(f"[UYARI] Ahmet Amca'dan boş ses dosyası geldi.")
            return {
                "user_transcription": "Ses algılanamadı.",
                "text": "Ses algılanamadı.",
                "ai_response": "Ahmet Amca, sesin geldi ama ahizeye tam üfleyemedin galiba, sesini duyamadım. Tekrar söyler misin?",
                "response": "Ahmet Amca, sesin geldi ama ahizeye tam üfleyemedin galiba, sesini duyamadım. Tekrar söyler misin?"
            }

        # 2. Tarayıcı uzantısını yakala, yoksa varsayılan olarak .wav yap
        ext = os.path.splitext(file.filename)[1] if file.filename else ".wav"
        if not ext or ext == ".blob":
            ext = ".wav"  # Groq'un tanıması için zorunlu uzantı
            
        custom_filename = f"audio{ext}"

        # 3. Diske yazmak yerine veriyi hafızada sanal bir dosya haline getir
        audio_file_like = io.BytesIO(audio_bytes)

        # 4. Groq Whisper API'sine sanal dosyayı gönder
        transcription = groq_client.audio.transcriptions.create(
            file=(custom_filename, audio_file_like.read()), # Uzantı bilgisini tuple olarak geçiyoruz
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
            # 5. Llama ile sevecen cevap üret
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

    except Exception as e:
        # Burası patlarsa terminale tam olarak ne hatası olduğunu yazdırıyoruz:
        print(f"[KRİTİK HATA] Ses işlenirken bir sorun oluştu: {str(e)}")
        user_text = "Ses dosyası işlenirken teknik hata oluştu."
        ai_response = "Ahmet Amca sesini tam alamadım, hattım kesildi galiba. İyi misin, her şey yolunda mı?"
    
    return {
        "user_transcription": user_text,
        "text": user_text,
        "ai_response": ai_response,
        "response": ai_response,
        "message": ai_response
    }


@app.post("/api/checkin")
async def daily_checkin(data: CheckinModel):
    print(f"[LOG] Ahmet Amca bugün kendini nasıl hissediyor -> {data.mood}")
    return {"status": "success"}

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