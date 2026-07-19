# Yanımda Al — Canlıya Alma (PR-3c)

Bu rehber backend'i **Render Web Service**, frontend'i **Render Static Site** (veya Vercel) ile yayınlar.

## 1. Hazırlık

1. `.env.example` dosyasını kopyalayın: `backend/.env` (lokal) ve Render Dashboard → Environment.
2. `frontend/config.js` içindeki `PRODUCTION_API_ORIGIN` değerini kendi Render API URL'inizle güncelleyin  
   (ör. `https://yanimda-al-backend.onrender.com`).
3. Alternatif (kod değiştirmeden): frontend HTML'e  
   `<meta name="yanimda-api" content="https://SIZIN-API.onrender.com">`  
   veya sayfayı `?api=https://SIZIN-API.onrender.com` ile açın.

## 2. Backend (Render Web Service)

**Seçenek A — Blueprint**

1. [Render](https://render.com) → New → Blueprint → bu GitHub reposunu bağlayın.
2. `render.yaml` içindeki `yanimda-al-backend` servisini onaylayın.
3. Secret env'leri (GROQ, Supabase, Twilio) UI'dan girin.

**Seçenek B — Manuel**

| Alan | Değer |
|------|--------|
| Root Directory | `backend` |
| Build | `pip install -r ../requirements.txt` |
| Start | `uvicorn main:app --host 0.0.0.0 --port $PORT` |
| Health | `/docs` |

Free plan uyku (sleep) yapar; ilk istek 30–60 sn sürebilir.

## 3. Frontend (Static)

**Render Static Site**

| Alan | Değer |
|------|--------|
| Root Directory | `frontend` |
| Build | (boş / `echo ok`) |
| Publish | `.` |

**Vercel**

- Root: `frontend`
- Framework: Other
- Output: `.` (statik)

Deploy sonrası `config.js` PRODUCTION URL'inin API servisinize işaret ettiğini doğrulayın.

## 4. CORS / WebSocket

Backend varsayılanı: `CORS_ORIGINS=*` (MVP).  
Sıkılaştırmak için:

```
CORS_ORIGINS=https://yanimda-al-frontend.onrender.com,https://your-app.vercel.app
```

Aile paneli ve kiosk:

- Lokal: `ws://127.0.0.1:8000`
- Canlı: `wss://<api-host>` (`config.js` otomatik seçer)

## 5. Hızlı doğrulama

1. `GET https://<api>/docs` açılıyor mu?
2. Kiosk login / text-chat çalışıyor mu?
3. Aile paneli sağ üstte **Canlı** (WebSocket) görünüyor mu?
4. Eskalasyon → banner; ağrı ≥9 → `[SMS STUB]` veya Twilio?

## 6. Demo ipuçları

- Render free cold start için videoyu API'yi bir kez ısıttıktan sonra çekin.
- SMS demosu: `FAMILY_SMS_ENABLED=false` ile stub log yeterli; gerçek SMS için Twilio + `true`.
- DeepFace ağırdır; yüz tanıma Render free'de zaman aşımına düşebilir — demo için aile telefon girişi veya önceden ısınmış instance kullanın.
