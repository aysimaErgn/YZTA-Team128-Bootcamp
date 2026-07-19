"""Agent Task Routing — kural + Groq JSON / Pydantic karar + fail-safe companion."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Literal

from groq import Groq
from pydantic import BaseModel, Field, ValidationError

from orchestrator.prompts import ROUTER_SYSTEM

NextNode = Literal["companion", "health", "escalation"]
Urgency = Literal["low", "medium", "high"]


class RouterDecision(BaseModel):
    """Orchestrator yönlendirme kararı (structured output)."""

    next_node: NextNode = Field(
        description=(
            "Gidilecek ajan: companion=sohbet, health=ilaç/semptom/check-in, "
            "escalation=acil risk (düşme, nefes, bayılma)."
        )
    )
    urgency: Urgency = Field(default="low", description="Aciliyet seviyesi.")
    reason: str = Field(default="", description="Yönlendirme gerekçesi.")

    @property
    def intent(self) -> str:
        """Geriye uyum: graph/state 'intent' alanını kullanır."""
        return self.next_node


URGENT_PATTERNS = [
    r"d[uü][sş]t[uü]m",
    r"d[uü][sş]mek\s*[uü]zere",
    r"kalkam[ıi]yorum",
    r"yard[ıi]m\s*et",
    r"nefes\s*alam[ıi]yorum",
    r"bay[ıi]l",
    r"g[oö][gğ][uü]s\s*a[gğ]r[ıi]",
    r"acil",
    r"ambulans",
    r"kanama",
    r"bilincimi\s*kaybett",
    r"ba[sş][ıi]m\s*[cç]ok\s*d[oö]n",
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
    r"nas[ıi]ls[ıi]n",
]


def _normalize(text: str) -> str:
    return (text or "").strip().lower()


def rule_based_intent(message: str) -> str | None:
    """Acil → escalation; güçlü sağlık → health; aksi None (LLM'e bırak)."""
    text = _normalize(message)
    if not text:
        return None

    for pattern in URGENT_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return "escalation"

    health_hits = sum(1 for pattern in HEALTH_PATTERNS if re.search(pattern, text, re.IGNORECASE))
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


def _parse_router_decision(raw: str) -> RouterDecision:
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

    # Eski şema: intent → next_node
    if "next_node" not in data and "intent" in data:
        data = {**data, "next_node": data.get("intent")}

    raw_node = str(data.get("next_node") or "companion").strip().lower()
    # LLM bazen şemayı aynen yapıştırır: "companion|health|escalation"
    if "|" in raw_node or raw_node not in {"companion", "health", "escalation"}:
        picked = None
        for part in re.split(r"[|\s,/]+", raw_node):
            if part in {"companion", "health", "escalation"}:
                picked = part
                break
        raw_node = picked or "companion"
    data["next_node"] = raw_node

    return RouterDecision.model_validate(data)


def llm_classify_intent(
    message: str,
    history: list[dict[str, Any]] | None = None,
    *,
    shared_hint: str | None = None,
) -> RouterDecision:
    client = _get_groq_client()
    if not client:
        return RouterDecision(
            next_node="companion",
            urgency="low",
            reason="GROQ_API_KEY yok; varsayılan companion",
        )

    history_lines = ""
    for item in (history or [])[-6:]:
        role = item.get("role", "user")
        content = item.get("content", "")
        history_lines += f"{role}: {content}\n"

    user_payload = (
        f"Sohbet geçmişi:\n{history_lines or '(yok)'}\n\n"
        f"Son kullanıcı mesajı:\n{message}"
    )
    if shared_hint:
        user_payload += f"\n\nOrtak sağlık bağlamı (ipucu):\n{shared_hint}"

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
    return _parse_router_decision(raw)


def resolve_intent(
    message: str,
    history: list[dict[str, Any]] | None = None,
    *,
    shared_hint: str | None = None,
) -> dict[str, str]:
    """
    Görev yönlendirme sırası:
    1) Kural: acil → escalation, güçlü sağlık → health
    2) LLM JSON → RouterDecision (Pydantic)
    3) Fail-safe → companion
    """
    ruled = rule_based_intent(message)
    if ruled == "escalation":
        decision = RouterDecision(
            next_node="escalation",
            urgency="high",
            reason="Kural tabanlı acil durum kalıbı",
        )
    elif ruled == "health":
        decision = RouterDecision(
            next_node="health",
            urgency="medium",
            reason="Kural tabanlı sağlık/ilaç kalıbı",
        )
    else:
        try:
            decision = llm_classify_intent(message, history, shared_hint=shared_hint)
        except (Exception, ValidationError) as error:
            print(f"[ORCHESTRATOR] Intent LLM hatası: {error}")
            decision = RouterDecision(
                next_node="companion",
                urgency="low",
                reason="Sınıflandırma başarısız, varsayılan refakat",
            )

    return {
        "intent": decision.next_node,
        "next_node": decision.next_node,
        "urgency": decision.urgency,
        "reason": decision.reason,
    }


def orchestrator_router(state: dict[str, Any]) -> NextNode:
    """
    LangGraph conditional edge için: sonraki düğüm adını döner.
    (route_node State'i doldurduktan sonra pick_agent ile de kullanılır.)
    """
    intent = (state.get("intent") or "").strip().lower()
    if intent in {"companion", "health", "escalation"}:
        return intent  # type: ignore[return-value]

    result = resolve_intent(
        state.get("user_message") or state.get("user_input") or "",
        state.get("chat_history"),
    )
    return result["next_node"]  # type: ignore[return-value]
