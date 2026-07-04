import os
from dotenv import load_dotenv
from supabase import create_client, Client
from datetime import datetime

# .env dosyasındaki gizli bilgileri yükle
load_dotenv()

URL = os.getenv("SUPABASE_URL")
KEY = os.getenv("SUPABASE_KEY")

# Supabase bağlantısını kur
supabase: Client = create_client(URL, KEY)

# --- TRELLO GÖREVİ 1: KULLANICI BİLGİLERİNİN TUTULMASI ---
def add_elder(full_name, phone, city, preferred_language="tr"):
    data = {
        "full_name": full_name,
        "phone": phone,
        "city": city,
        "preferred_language": preferred_language
    }
    response = supabase.table("elders").insert(data).execute()
    return response.data

# --- TRELLO GÖREVİ 2: SOHBET GEÇMİŞİ TUTULMASI ---
def save_message(conversation_id: str, role: str, content: str, user_id: str = None):
    try:
        # 1. Oturum kontrolü
        conv_check = supabase.table("conversations").select("id").eq("id", conversation_id).execute()
        
        # 2. Eğer oturum yoksa sadece ID ile oluştur (title sütununu zorlamıyoruz)
        if not conv_check.data:
            supabase.table("conversations").insert({
                "id": conversation_id
            }).execute()
            print(f"[OTURUM OLUŞTURULDU] {conversation_id} aktif.")

        # 3. Mesajı kaydet (user_id varsa, mesajı gerçek kayıtlı kullanıcıya bağlıyoruz)
        message_payload = {
            "conversation_id": conversation_id,
            "role": role,
            "content": content
        }
        if user_id:
            message_payload["user_id"] = user_id

        supabase.table("messages").insert(message_payload).execute()
        
    except Exception as e:
        print(f"[VERİTABANI HATASI] Mesaj kaydedilemedi: {str(e)}")



def get_conversation_history(conversation_id):
    response = supabase.table("messages") \
        .select("*") \
        .eq("conversation_id", conversation_id) \
        .order("created_at", desc=False) \
        .execute()
    return response.data

# --- TRELLO GÖREVİ 3: GÜNLÜK DURUM (CHECK-IN) KAYITLARININ TUTULMASI ---
def save_checkin(conversation_id: str, mood: str):
    try:
        # 1. Oturum kontrolü
        conv_check = supabase.table("conversations").select("id").eq("id", conversation_id).execute()
        
        # 2. Eğer oturum yoksa sadece ID ile oluştur
        if not conv_check.data:
            supabase.table("conversations").insert({
                "id": conversation_id
            }).execute()
            print(f"[OTURUM OLUŞTURULDU] Check-in için {conversation_id} aktif.")

        # 3. Durumu kaydet
        supabase.table("checkins").insert({
            "conversation_id": conversation_id,
            "mood": mood
        }).execute()
        
    except Exception as e:
        print(f"[VERİTABANI HATASI] Check-in kaydedilemedi: {str(e)}")
        raise e

def get_checkin_history(conversation_id, limit=10):
    """Belirli bir kullanıcının geçmiş check-in kayıtlarını en yeniden eskiye doğru getirir."""
    response = supabase.table("checkins") \
        .select("*") \
        .eq("conversation_id", conversation_id) \
        .order("created_at", desc=True) \
        .limit(limit) \
        .execute()
    return response.data

# --- TRELLO GÖREVİ: CHECK-IN EKSİKLİĞİ TESPİTİ ---
def get_today_checkin_status(conversation_id):
    """
    Bugün (yerel gün başlangıcından şu ana kadar) bu oturum için
    check-in yapılıp yapılmadığını kontrol eder.
    Yapılmışsa en son kaydı, yapılmamışsa None döner.
    """
    today_start = datetime.now().strftime("%Y-%m-%dT00:00:00")

    response = supabase.table("checkins") \
        .select("*") \
        .eq("conversation_id", conversation_id) \
        .gte("created_at", today_start) \
        .order("created_at", desc=True) \
        .limit(1) \
        .execute()

    if response.data:
        return response.data[0]
    return None