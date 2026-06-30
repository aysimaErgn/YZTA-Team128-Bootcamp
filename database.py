import os
from dotenv import load_dotenv
from supabase import create_client, Client

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
def save_message(conversation_id, role, content):
    """role: 'user' veya 'assistant' olmalı"""
    data = {
        "conversation_id": conversation_id,
        "role": role, 
        "content": content
    }
    response = supabase.table("messages").insert(data).execute()
    return response.data

def get_conversation_history(conversation_id):
    response = supabase.table("messages") \
        .select("*") \
        .eq("conversation_id", conversation_id) \
        .order("created_at", desc=False) \
        .execute()
    return response.data