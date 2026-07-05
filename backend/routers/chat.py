import os
import io
from datetime import datetime
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
from groq import Groq
from database import save_message, supabase

router = APIRouter(tags=["Chat"])

groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

def get_elderly_name(conversation_id: str) -> str:
    try:
        resp = supabase.table("users").select("name").eq("id", conversation_id).execute()
        if resp.data:
            return resp.data[0]["name"]
    except Exception as e:
        print("İsim çekilemedi:", e)
    return "kullanıcı"

def build_system_prompt(elderly_name: str) -> str:
    return (
        "Sen 'Yanımda Al' projesinde yalnız yaşayan yaşlılara destek olan sevecen, "
        f"sabırlı ve neşeli bir dijital refakatçi ajansın. Karşındaki kişi 65 yaş üstü "
        f"{elderly_name}. Cümlelerin çok uzun olmasın, onun durumunu sor, empati yap ve "
        "onu motive et. Tıbbi teşhis veya tedavi önerisi verme."
    )

class TextMessageModel(BaseModel):
    conversation_id: str  # Artık zorunlu ve dinamik
    message: str

class SummaryRequestModel(BaseModel):
    conversation_id: str




@router.post("/api/text-chat")
async def text_chat(data: TextMessageModel):
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": build_system_prompt(get_elderly_name(data.conversation_id))},
                {"role": "user", "content": data.message}
            ],
            max_tokens=150,
            temperature=0.7
        )
        ai_response = response.choices[0].message.content
        
        # İstekle gelen dinamik id'yi kaydediyoruz
        save_message(conversation_id=data.conversation_id, role="user", content=data.message)
        save_message(conversation_id=data.conversation_id, role="assistant", content=ai_response)
        
        return {"ai_response": ai_response}
    except Exception as e:
        gizli_hata = f"SİSTEM HATASI BULUNDU: {str(e)}"
        print(gizli_hata)
        return {"ai_response": gizli_hata}

@router.post("/api/voice-chat")
async def voice_chat(
    file: UploadFile = File(...), 
    conversation_id: str = Form(...)  # Frontend ses gönderirken bunu da form datası olarak ekleyecek
):
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
                    {"role": "system", "content": build_system_prompt(get_elderly_name(conversation_id))},
                    {"role": "user", "content": user_text}
                ],
                max_tokens=150,
                temperature=0.7
            )
            ai_response = response.choices[0].message.content
            
            # Dinamik id buraya da işlendi
            save_message(conversation_id=conversation_id, role="user", content=user_text)
            save_message(conversation_id=conversation_id, role="assistant", content=ai_response)

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

@router.get("/api/conversations")
async def get_conversations():
    try:
        # En son mesaj atılan oturumları (conversation_id) listeliyoruz
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

                # Profesyonel olarak her oturum kendi UUID'si ve tarihiyle listelenir
                unique_conversations.append({
                    "conversation_id": c_id, 
                    "title": f"Sohbet - {formatted_date}"
                })
        return unique_conversations
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/conversations/{conversation_id}")
async def get_chat_history(conversation_id: str):
    try:
        response = supabase.table("messages").select("role", "content").eq("conversation_id", conversation_id).order("created_at", desc=False).execute()
        return response.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    




@router.post("/api/family/generate-ai-summary")
async def generate_ai_summary(data: SummaryRequestModel):
    try:
        # 1. Yaşlının bu oturuma ait son 15 mesajını veritabanından çekiyoruz
        messages_response = supabase.table("messages") \
            .select("role, content") \
            .eq("conversation_id", data.conversation_id) \
            .order("created_at", desc=True) \
            .limit(15) \
            .execute()
        
        if not messages_response.data:
            return {
                "success": True, 
                "summary": "Bugün henüz dijital refakatçi ile bir sohbet gerçekleşmedi. Yaşlınızın genel durumu stabil görünüyor."
            }
        
        # Mesajları kronolojik sıraya sokuyoruz (en eskiden en yeniye)
        chat_history = list(reversed(messages_response.data))
        
        # 2. LLM için konuşma metnini hazırlıyoruz
        formatted_history = ""
        for msg in chat_history:
            sender = "Ahmet Amca" if msg["role"] == "user" else "Asistan"
            formatted_history += f"{sender}: {msg['content']}\n"

        # 3. Groq modeline aileyi bilgilendirecek şekilde analiz yaptırıyoruz
        AI_FAMILY_PROMPT = (
            "Sen 'Yanımda Al' projesinin arka plandaki analiz zekasısın. "
            "Sana yalnız yaşayan Ahmet Amca ile dijital refakatçi asistan arasındaki son sohbet geçmişi verilecek. "
            "Bu konuşmaları analiz ederek Ahmet Amca'nın ailesine/refakatçisine ulaştırılacak kısa, "
            "samimi ama bilgilendirici bir günlük özet çıkar. Ahmet Amca'nın modunu, sağlığıyla veya "
            "ilaçlarıyla ilgili verdiği ipuçlarını, eğer varsa bir sıkıntısını veya talebini mutlaka belirt. "
            "Tıbbi kararlar verme, doğrudan durumu özetle. Maksimum 3-4 cümle olsun."
        )

        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": AI_FAMILY_PROMPT},
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