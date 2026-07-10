import os
import sys
from datetime import datetime, timedelta

# backend içindeki .env veya ana dizindeki .env'yi yükle
sys.path.append(os.path.abspath("backend"))
from dotenv import load_dotenv
load_dotenv() 
load_dotenv("backend/.env")

from supabase import create_client, Client

URL = os.getenv("SUPABASE_URL")
KEY = os.getenv("SUPABASE_KEY")

if not URL or not KEY:
    print("HATA: SUPABASE_URL veya SUPABASE_KEY bulunamadı. Lütfen .env dosyanızı kontrol edin.")
    sys.exit(1)

supabase: Client = create_client(URL, KEY)

def create_test_data():
    try:
        # 1. Yaşlı Birey Ekle
        print("1. Test kullanıcısı oluşturuluyor...")
        elder_response = supabase.table("elders").insert({
            "full_name": "Test Ahmet Amca",
            "phone": "5551234567",
            "city": "İstanbul"
        }).execute()
        
        elder_id = elder_response.data[0]["id"]
        
        # 2. İlaç Ekle
        print("2. 'Test Vitamin' adında bir ilaç ekleniyor...")
        med_response = supabase.table("medications").insert({
            "elder_id": elder_id,
            "name": "Test Vitamin",
            "dosage": "100mg",
            "form": "Hap"
        }).execute()
        
        med_id = med_response.data[0]["id"]
        
        # 3. Takvimleri Ayarla
        now = datetime.now()
        
        # A) 2 Dakika Sonrası (Tablet Popup Uyanma Testi)
        two_mins_later = (now + timedelta(minutes=2)).strftime("%H:%M:%S")
        
        # B) 31 Dakika Öncesi (Eskalasyon/Tehlike Testi)
        thirty_one_mins_ago = (now - timedelta(minutes=31)).strftime("%H:%M:%S")
        
        current_weekday = now.isoweekday() # 1: Pzt, 7: Paz
        
        print(f"3. Saat {two_mins_later} ve {thirty_one_mins_ago} için takvim ayarlanıyor...")
        
        # Hatırlatma Zamanı
        supabase.table("medication_schedules").insert({
            "medication_id": med_id,
            "time_of_day": two_mins_later,
            "days_of_week": [current_weekday]
        }).execute()
        
        # Eskalasyon Zamanı
        supabase.table("medication_schedules").insert({
            "medication_id": med_id,
            "time_of_day": thirty_one_mins_ago,
            "days_of_week": [current_weekday]
        }).execute()

        print("\n" + "="*50)
        print("✅ TEST VERİLERİ BAŞARIYLA EKLENDİ!")
        print("="*50)
        print(f"Bu ID'yi frontend'de (localStorage 'user_id' olarak) test için kullanabilirsiniz:")
        print(f"KULLANICI (ELDER) ID: {elder_id}")
        print("-"*50)
        print(f"👉 1. TEST (Eskalasyon): Arkada çalışan scheduler 1 dakika içinde {thirty_one_mins_ago} tarihli ilacı bulup konsola 'ESKALASYON' yazacak ve alerts tablosuna kaydedecek.")
        print(f"👉 2. TEST (Hatırlatma): Backend çalışırken, tablet arayüzünüzü açarsanız saat {two_mins_later} olduğunda otomatik 'İlaç Saati' ekranı fırlayacaktır.")

    except Exception as e:
        print(f"Veri eklerken hata oluştu: {e}")

if __name__ == "__main__":
    create_test_data()
