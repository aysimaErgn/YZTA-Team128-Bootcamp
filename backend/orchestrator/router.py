"""Intent yönlendirme — kural tabanlı acil durum + LLM sınıflandırma."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from groq import Groq

from orchestrator.prompts import ROUTER_SYSTEM

URGENT_PATTERNS = [
    r"d[uü][sş]t[uü]m",
    r"kalkam[ıi]yorum",
    r"yard[ıi]m\s*et",
    r"nefes\s*alam[ıi]yorum",
    r"bay[ıi]l",
    r"g[oö][gğ][uü]s\s*a[gğ]r[ıi]",
    r"acil",
    r"ambulans",
    r"kanama",
    r"bilincimi\s*kaybett",
]

HEALTH_PATTERNS = [
    r"ila[cç]",
    r"hap",
    r"doz",
    r"i[cç]tim",
    r"check[\s-]?in",
    r"ba[sş][ıi]m\s*a[gğ]r",
    r"semptom",
    r"a[gğ]r[ıi]",
    r"tansiyon",
    r"[sş]eker",
    r"vitamin",
    r"nas[ıi]ls[ıi]n",  # check-in bağlamı için zayıf; LLM tamamlar
]


def _normalize(text: str) -> str:
    return (text or "").strip().lower()


def rule_based_intent(message: str) -> str | None:
    """Acil durumda escalation, güçlü sağlık sinyalinde health döner; aksi None."""
    text = _normalize(message)
    if not text:
        return None

    for pattern in URGENT_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return "escalation"

    health_hits = sum(1 for pattern in HEALTH_PATTERNS if re.search(pattern, text, re.IGNORECASE))
    # "nasılsın" tek başına sohbet olabilir; ilaç/ağrı ile birlikteyse health
    strong_health = any(
        re.search(p, text, re.IGNORECASE)
        for p in [r"ila[cç]", r"hap", r"doz", r"i[cç]tim", r"a[gğ]r[ıi]", r"tansiyon", r"semptom"]
    )
    if strong_health or health_hits >= 2:
        return "health"

    return None


def _get_groq_client() -> Groq | None:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return None
    return Groq(api_key=api_key)


def _parse_intent_json(raw: str) -> dict[str, str]:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise
        data = json.loads(match.group(0))

    intent = str(data.get("intent", "companion")).strip().lower()
    if intent not in {"companion", "health", "escalation"}:
        intent = "companion"
    urgency = str(data.get("urgency", "low")).strip().lower()
    if urgency not in {"low", "medium", "high"}:
        urgency = "low"
    reason = str(data.get("reason", "")).strip()
    return {"intent": intent, "urgency": urgency, "reason": reason}


def llm_classify_intent(message: str, history: list[dict[str, Any]] | None = None) -> dict[str, str]:
    client = _get_groq_client()
    if not client:
        return {"intent": "companion", "urgency": "low", "reason": "GROQ_API_KEY yok"}

    history_lines = ""
    for item in (history or [])[-6:]:
        role = item.get("role", "user")
        content = item.get("content", "")
        history_lines += f"{role}: {content}\n"

    user_payload = (
        f"Sohbet geçmişi:\n{history_lines or '(yok)'}\n\n"
        f"Son kullanıcı mesajı:\n{message}"
    )

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": ROUTER_SYSTEM},
            {"role": "user", "content": user_payload},
        ],
        temperature=0.1,
        max_tokens=120,
    )
    raw = response.choices[0].message.content or ""
    return _parse_intent_json(raw)


def resolve_intent(message: str, history: list[dict[str, Any]] | None = None) -> dict[str, str]:
    """Önce kural tabanlı acil/sağlık, sonra LLM; hata olursa companion."""
    ruled = rule_based_intent(message)
    if ruled == "escalation":
        return {
            "intent": "escalation",
            "urgency": "high",
            "reason": "Kural tabanlı acil durum kalıbı",
        }
    if ruled == "health":
        return {
            "intent": "health",
            "urgency": "medium",
            "reason": "Kural tabanlı sağlık/ilaç kalıbı",
        }

    try:
        return llm_classify_intent(message, history)
    except Exception as error:
        print(f"[ORCHESTRATOR] Intent LLM hatası: {error}")
        return {
            "intent": "companion",
            "urgency": "low",
            "reason": "Sınıflandırma başarısız, varsayılan refakat",
        }
