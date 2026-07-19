# Yanımda Al — Orkestratör

Sohbet girdilerini **Refakat / Sağlık / Eskalasyon** ajanlarına yönlendirir.
Aşama 2 ile **ortak hafıza** (kısa + uzun + Supabase yapısal) eklendi.

## Aç / kapat

`.env`:

```
ORCHESTRATOR_ENABLED=true
```

## Hafıza katmanları (Aşama 2)

| Katman | Teknoloji | Ne tutar |
|--------|-----------|----------|
| Kısa süreli | LangGraph `AgentState` + Supabase `messages` | Son mesajlar, intent, bayraklar |
| Uzun süreli | JSON (varsayılan) / **Chroma** (`MEMORY_USE_CHROMA=true`) | İlgi alanları, alışkanlıklar |
| Yapısal | Supabase | Profil, bugünkü ilaçlar, check-in |
| **Ajanlar arası** | `shared_health_context` + `detected_mood` | Sağlık → Refakat/Eskalasyon paylaşımı |

`load_context` son check-in’leri Supabase’den okuyup State’e enjekte eder.
Sağlık ajanı turunda `shared_health_context` güncellenir; refakat ajanı prompt’ta okur.

## Akış

```
/api/text-chat | voice
  → load_context (anı + ilaç/check-in + shared health)
  → router (Agent Task Routing: kural → LLM JSON/Pydantic → companion|health|escalation)
  → companion | health | escalation
  → health: tool + anomali
       └─ escalation_needed → escalation (PR-2)
```

## Agent Task Routing

| Sıra | Mekanizma | Örnek |
|------|-----------|--------|
| 1 | Kural (acil) | “Düştüm kalkamıyorum” → `escalation` |
| 2 | Kural (sağlık) | “İlacımı içtim” → `health` |
| 3 | Groq JSON → `RouterDecision` | “Eski günleri anlat” → `companion` |
| 4 | Fail-safe | API hatası → `companion` |

`route_node` → `intent` + `active_agent`; `pick_agent` / `orchestrator_router` conditional edge.

## PR-2 — Sağlık araçları ve eşik

| Ayar | Varsayılan | Anlamı |
|------|------------|--------|
| `HEALTH_PAIN_ESCALATION_THRESHOLD` | `7` | Ağrı ≥ eşik → `escalation_needed` |

Araçlar (`orchestrator/tools/health_tools.py`):

- `record_medication_taken` → `medication_logs` (`record_manual_taken`)
- `record_daily_checkin` → `save_checkin` (mood içinde `ağrı:N/10`)
- `should_escalate_health` → ağrı / tehlike / yanlış ilaç

## PR-3a — Aile WebSocket

| Endpoint | Rol |
|----------|-----|
| `/ws/client/{elder_id}?role=kiosk` | Kiosk ilaç hatırlatması |
| `/ws/client/{elder_id}?role=family` | Aile paneli kritik uyarı |
| `/ws/medication/{elder_id}` | Eski kiosk yolu (aynı oda) |

`escalation_node` → `alerts` insert + `CRITICAL_HEALTH_EVENT` → `broadcast_to_family`.

## PR-3b — Seçici SMS (Twilio / stub)

| Koşul | SMS? |
|-------|------|
| Ağrı 7–8 (WS eskalasyonu) | Hayır |
| Ağrı ≥ 9 (`SMS_PAIN_ESCALATION_THRESHOLD`) | Evet |
| `is_danger` / yanlış ilaç | Evet |
| Router `intent=escalation` + `urgency=high` (düşme vb.) | Evet |

Env:

```
FAMILY_SMS_ENABLED=false
SMS_PAIN_ESCALATION_THRESHOLD=9
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_PHONE_NUMBER=
FAMILY_SMS_OVERRIDE_PHONE=   # opsiyonel demo
```

Telefon: `users.family_phone` (+ isteğe bağlı `family_sms_enabled`).

## PR-3c — Canlıya alma

- `.env.example` — Groq / Supabase / Twilio / eşikler
- `frontend/config.js` — lokal vs `wss://` / `https://` API
- `render.yaml` + `DEPLOY.md` — Render blueprint rehberi
- `CORS_ORIGINS` env (varsayılan `*`)

## Demo

| Mesaj | Beklenen |
|-------|----------|
| Torunumla satranç oynamayı severim | companion + hafızaya yaz |
| Sabah ilacım olan Apranax'ı az önce içtim | health → ilaç log → END |
| Belim çok kötü ağrıyor, ağrı seviyem 8 | health → check-in → escalation |
| Düştüm kalkamıyorum | escalation (router) |

## Test

```bash
cd backend
python tests/test_orchestrator_router.py
python tests/test_agent_routing.py
python tests/test_orchestrator_memory.py
python tests/test_orchestrator_health_pr2.py
python tests/test_family_websocket_pr3a.py
python tests/test_sms_escalation_pr3b.py
python tests/test_shared_agent_context.py
```
