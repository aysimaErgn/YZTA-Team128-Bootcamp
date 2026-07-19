import base64
import json
import os
import re

from groq import Groq

# Groq: llama-3.2-*-vision-preview 14 Nisan 2025'te kapatıldı.
# Güncel vision modeli: https://console.groq.com/docs/vision
VISION_MODEL = os.environ.get(
    "GROQ_VISION_MODEL",
    "qwen/qwen3.6-27b",
)

RECOGNITION_PROMPT = (
    "Bu görüntüde bir ilaç kutusu, blister veya ilaç şişesi olabilir. "
    "Görünen ilacın Türkçe adını veya kutuda yazan marka/etken madde adını belirle. "
    "Tıbbi teşhis veya doz önerisi verme. "
    "Yalnızca şu JSON formatında cevap ver, başka metin ekleme:\n"
    '{"medication_name": "...", "confidence": "high|medium|low", "notes": "..."}\n'
    "İlaç net değilse medication_name değerini Bilinmiyor yap."
)


def get_groq_client() -> Groq:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY tanımlı değil.")
    return Groq(api_key=api_key)


def normalize_name(value: str) -> str:
    normalized = value.strip().lower()
    replacements = {"ı": "i", "İ": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g", "ü": "u", "Ü": "u", "ö": "o", "Ö": "o", "ç": "c", "Ç": "c"}
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)
    return re.sub(r"\s+", " ", normalized)


def names_match(recognized: str, expected: str) -> bool:
    recognized_norm = normalize_name(recognized)
    expected_norm = normalize_name(expected)
    if not recognized_norm or recognized_norm == "bilinmiyor":
        return False
    if recognized_norm == expected_norm:
        return True
    return expected_norm in recognized_norm or recognized_norm in expected_norm


def parse_model_json(raw_text: str) -> dict:
    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


def recognize_medication_from_image(image_bytes: bytes, expected_name: str | None = None) -> dict:
    if not image_bytes or len(image_bytes) < 100:
        return {
            "recognized_med": "Bilinmiyor",
            "confidence": "low",
            "is_match": False if expected_name else None,
            "message": "Fotoğraf boş veya okunamadı. Lütfen kutuyu tekrar çekin.",
        }

    image_base64 = base64.b64encode(image_bytes).decode("utf-8")
    mime_type = "image/jpeg"
    if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        mime_type = "image/png"
    elif image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        mime_type = "image/webp"

    client = get_groq_client()
    response = client.chat.completions.create(
        model=VISION_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": RECOGNITION_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{image_base64}"},
                    },
                ],
            }
        ],
        temperature=0.2,
        max_tokens=300,
    )

    raw_content = response.choices[0].message.content or ""
    parsed = parse_model_json(raw_content)
    recognized_med = str(parsed.get("medication_name", "Bilinmiyor")).strip() or "Bilinmiyor"
    confidence = str(parsed.get("confidence", "medium")).strip().lower()
    notes = str(parsed.get("notes", "")).strip()

    is_match = None
    message = f"Tanınan ilaç: {recognized_med}."
    if notes:
        message = f"{message} {notes}"

    if expected_name:
        is_match = names_match(recognized_med, expected_name)
        if is_match:
            message = f"Doğru ilaç tanındı: {recognized_med}."
        else:
            message = (
                f"Beklenen ilaç '{expected_name}', tanınan '{recognized_med}'. "
                "Lütfen doğru kutuyu gösterin."
            )

    return {
        "recognized_med": recognized_med,
        "confidence": confidence,
        "is_match": is_match,
        "message": message,
    }
