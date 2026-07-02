import base64
import numpy as np
import cv2
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from deepface import DeepFace
from database import supabase

router = APIRouter(tags=["Authentication"])

class FaceAuthRequest(BaseModel):
    image_data: str

class FullRegisterRequest(BaseModel):
    elderly: dict
    family: dict

def base64_to_image(base64_string):
    try:
        if "," in base64_string:
            base64_string = base64_string.split(",")[1]
        img_bytes = base64.b64decode(base64_string)
        img_np = np.frombuffer(img_bytes, dtype=np.uint8)
        img = cv2.imdecode(img_np, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Resim decode edilemedi, veri bos veya hatali.")
        rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        return rgb_img
    except Exception as e:
        print("!!! BASE64 CEVIRME HATASI:", str(e))
        raise HTTPException(status_code=400, detail="Fotoğraf verisi işlenemedi.")

# 1. YÜZ VEKTÖRÜ ÇIKARMA ENDPOINT'İ
@router.post("/auth/register-face")
async def register_face(request: FaceAuthRequest):
    try:
        rgb_image = base64_to_image(request.image_data)
        embeddings_data = DeepFace.represent(
            img_path=rgb_image, 
            model_name="VGG-Face", 
            enforce_detection=False, 
            detector_backend="opencv"
        )
        if not embeddings_data or len(embeddings_data) == 0:
            raise HTTPException(status_code=400, detail="Fotoğrafta yüz tespit edilemedi!")
            
        elderly_face_vector = embeddings_data[0]["embedding"]
        return {"success": True, "message": "Yüz imzası başarıyla çıkarıldı.", "face_vector": elderly_face_vector}
    except Exception as e:
        print("!!! REGISTER FACE HATASI:", str(e))
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=400, detail=f"Yüz analizi başarısız: {str(e)}")

# 2. TÜM VERİLERİ SUPABASE'E YAZAN ASIL KAYIT ENDPOINT'İ
@router.post("/auth/register")
async def register_all(request: FullRegisterRequest):
    try:
        insert_data = {
            "name": request.elderly.get("name"),
            "age": int(request.elderly.get("age")) if request.elderly.get("age") else None,
            "face_vector": request.elderly.get("face_vector"),
            "family_name": request.family.get("name"),
            "family_phone": str(request.family.get("phone")),
            "family_password": str(request.family.get("password"))
        }
        
        response = supabase.table("users").insert(insert_data).execute()
        return {"success": True, "message": "Kullanıcı ve refakatçi kaydı başarıyla oluşturuldu."}
    except Exception as e:
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print("!!! SUPABASE VERİTABANI YAZMA HATASI DETAYI:", str(e))
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        raise HTTPException(status_code=400, detail=f"Veritabanı kayıt hatası: {str(e)}")

# 3. YÜZ TANIMA İLE GİRİŞ ENDPOINT'İ
@router.post("/auth/face-login")
async def face_login(request: FaceAuthRequest):
    try:
        current_rgb_image = base64_to_image(request.image_data)
        current_embeddings = DeepFace.represent(
            img_path=current_rgb_image, 
            model_name="VGG-Face", 
            enforce_detection=False, 
            detector_backend="opencv"
        )
        
        if not current_embeddings or len(current_embeddings) == 0:
            raise HTTPException(status_code=400, detail="Yüz algılanamadı. Lütfen kameraya yaklaşın.")
            
        login_face_encoding = current_embeddings[0]["embedding"]
        users_response = supabase.table("users").select("id, name, face_vector").not_.is_("face_vector", "null").execute()
        
        for user in users_response.data:
            saved_face_vector = user["face_vector"]
            if not saved_face_vector or len(saved_face_vector) != len(login_face_encoding):
                continue
                
            distance = DeepFace.verification.CosineDistance.calculate_distance(login_face_encoding, saved_face_vector)
            print(f"-> {user['name']} için ölçülen mesafe: {distance}")
            
            if distance <= 0.40: 
                return {
                    "success": True,
                    "message": f"Giriş Başarılı. Hoş geldin {user['name']}",
                    "user_id": user["id"],
                    "name": user["name"]
                }
                
        raise HTTPException(status_code=401, detail="Yüz tanınamadı! Kayıtlı kullanıcı bulunamadı.")
    except Exception as e:
        print("!!! FACE-LOGIN DETAYLI HATA LOGU:", str(e))
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=400, detail=f"Giriş esnasında hata: {str(e)}")
    

# authorization.py dosyasının en altına eklenecek yeni model ve endpoint:

class CredentialsAuthRequest(BaseModel):
    name: str
    age: int

@router.post("/auth/credentials-login")
async def credentials_login(request: CredentialsAuthRequest):
    try:
        print(f"--- GIRIS DENEMESI --- Gelen Isim: '{request.name}', Yas: {request.age}")
        
        # Supabase'den tüm kullanıcıların sadece id, name ve age alanlarını çekiyoruz
        response = supabase.table("users").select("id", "name", "age").execute()
        user_data = response.data
        
        if not user_data:
            raise HTTPException(status_code=401, detail="Sistemde kayıtlı hiçbir kullanıcı yok.")

        # Python tarafında temiz ve Türkçe karakter uyumlu eşleştirme yapıyoruz
        matched_user = None
        for user in user_data:
            # İsimlerdeki boşlukları temizleyip küçük harfe çevirerek kıyaslıyoruz
            db_name = str(user.get("name")).strip().lower().replace("I", "ı").replace("İ", "i")
            input_name = str(request.name).strip().lower().replace("I", "ı").replace("İ", "i")
            
            if db_name == input_name and int(user.get("age")) == int(request.age):
                matched_user = user
                break

        if matched_user:
            print(f"✔️ Giriş Başarılı: {matched_user['name']}")
            return {
                "success": True,
                "message": f"Giriş Başarılı. Hoş geldin {matched_user['name']}",
                "user_id": matched_user["id"],
                "name": matched_user["name"]
            }
        else:
            print("❌ Eşleşen kullanıcı bulunamadı.")
            raise HTTPException(status_code=401, detail="Girdiğiniz ad veya yaş hatalı Ahmet Amca.")
            
    except Exception as e:
        print("!!! CREDENTIALS LOGIN COKTU:", str(e))
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=400, detail=f"Giriş esnasında hata: {str(e)}")