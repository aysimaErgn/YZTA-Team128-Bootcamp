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

def base64_to_image(base64_string):
    try:
        if "," in base64_string:
            base64_string = base64_string.split(",")[1]
        img_bytes = base64.b64decode(base64_string)
        img_np = np.frombuffer(img_bytes, dtype=np.uint8)
        img = cv2.imdecode(img_np, cv2.IMREAD_COLOR)
        # DeepFace de RGB formatında daha kararlı çalışır
        rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        return rgb_img
    except Exception as e:
        raise HTTPException(status_code=400, detail="Fotoğraf verisi işlenemedi.")

# 1. YÜZ KAYDETME ENDPOINT'İ (Kayıt Olurken Çalışır)
@router.post("/api/auth/register-face")
async def register_face(request: FaceAuthRequest):
    try:
        rgb_image = base64_to_image(request.image_data)
        
        # DeepFace ile yüzün 128 (veya seçilen modele göre) boyutlu embedding vektörünü çıkarıyoruz
        # VGG-Face modeli kararlı ve standart 128 boyutlu çıktı üretir, veritabanına tam uyar.
        embeddings_data = DeepFace.represent(
            img_path=rgb_image, 
            model_name="VGG-Face", 
            enforce_detection=True,
            detector_backend="opencv"
        )
        
        if not embeddings_data or len(embeddings_data) == 0:
            raise HTTPException(status_code=400, detail="Fotoğrafta yüz tespit edilemedi! Lütfen kameraya düzgün bakın.")
            
        elderly_face_vector = embeddings_data[0]["embedding"]
        
        return {
            "success": True, 
            "message": "Yüz imzası (DeepFace) başarıyla çıkarıldı.", 
            "face_vector": elderly_face_vector
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail="Yüz analizi başarısız oldu. Lütfen kameraya net bakın.")

# 2. YÜZ TANIMA İLE GİRİŞ ENDPOINT'İ (Giriş Yaparken Çalışır)
@router.post("/api/auth/face-login")
async def face_login(request: FaceAuthRequest):
    try:
        current_rgb_image = base64_to_image(request.image_data)
        
        # Giriş yapmaya çalışan kişinin anlık vektörünü alıyoruz
        current_embeddings = DeepFace.represent(
            img_path=current_rgb_image, 
            model_name="VGG-Face", 
            enforce_detection=True,
            detector_backend="opencv"
        )
        
        if not current_embeddings or len(current_embeddings) == 0:
            raise HTTPException(status_code=400, detail="Yüz algılanamadı. Lütfen kameraya yaklaşın.")
            
        login_face_encoding = current_embeddings[0]["embedding"]
        
        # Supabase'den kayıtlı yaşlı kullanıcıların yüz vektörlerini çekiyoruz
        users_response = supabase.table("users").select("id, name, face_vector").not_.is_("face_vector", "null").execute()
        
        # Matematiksel olarak en yakın yüzü bulmak için iki vektör arasındaki Kosinüs mesafesini ölçüyoruz
        for user in users_response.data:
            saved_face_vector = user["face_vector"]
            
            # İki vektör arasındaki mesafeyi (similarity) doğrulamak için DeepFace'in hazır doğrulama mantığını simüle ediyoruz
            # VGG-Face için Cosine mesafe sınırı (threshold) genellikle 0.40'tır. Altındaki değerler eşleşme demektir.
            distance = DeepFace.verification.CosineDistance.calculate_distance(login_face_encoding, saved_face_vector)
            
            if distance <= 0.40: # 0.40 ve altı -> Aynı kişi demektir
                return {
                    "success": True,
                    "message": f"Giriş Başarılı. Hoş geldin {user['name']}",
                    "user_id": user["id"]
                }
                
        raise HTTPException(status_code=401, detail="Yüz tanınamadı! Kayıtlı kullanıcı bulunamadı.")
    except Exception as e:
        raise HTTPException(status_code=400, detail="Yüz tanıma işlemi esnasında bir hata oluştu.")