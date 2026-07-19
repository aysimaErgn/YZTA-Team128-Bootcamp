"""Sağlık Ajanı — tool use + anomali → escalation_needed (PR-2)."""

from __future__ import annotations

import json
import os
import re

from groq import Groq

from orchestrator.memory.long_term import (
    extract_and_store_memories,
    format_memories_for_prompt,
)
from orchestrator.memory.structured import format_structured_for_prompt
from orchestrator.prompts import HEALTH_STUB_SYSTEM
from orchestrator.state import AgentState
from orchestrator.tools.health_tools import (
    HEALTH_PAIN_ESCALATION_THRESHOLD,
    record_daily_checkin,
    record_medication_taken,
    should_escalate_health,
)

DECISION_SYSTEM = (
    "Sen sağlık niyet analizörüsün. Kullanıcı mesajını JSON olarak sınıflandır. "
    "Başka metin yazma. Şema:\n"
    '{"action":"confirm_medication|log_health|none",'
    '"medication_name":string|null,'
    '"pain_level":1-10|null,'
    '"mood":string|null,'
    '"notes":string|null,'
    '"is_danger":boolean,'
    '"wrong_medication":boolean}\n'
    "Kurallar: ilaç içtim/aldım → confirm_medication; "
    "nasıl hissediyorum/ağrı/check-in → log_health; "
    "nefes darlığı, göğüs ağrısı, bayılma, düşme → is_danger true; "
    "yanlış ilaç içtim → wrong_medication true. "
    "Tıbbi teşhis koyma."
)


def _client() -> Groq:
    return Groq(api_key=os.environ.get("GROQ_API_KEY"))


def _parse_decision(raw: str) -> dict:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return {"action": "none", "pain_level": None, "is_danger": False, "wrong_medication": False}
        data = json.loads(match.group(0))

    action = str(data.get("action") or "none").strip().lower()
    if action not in {"confirm_medication", "log_health", "none"}:
        action = "none"

    pain = data.get("pain_level")
    try:
        pain_level = int(pain) if pain is not None and str(pain).strip() != "" else None
        if pain_level is not None:
            pain_level = max(0, min(10, pain_level))
    except (TypeError, ValueError):
        pain_level = None

    return {
        "action": action,
        "medication_name": data.get("medication_name"),
        "pain_level": pain_level,
        "mood": data.get("mood"),
        "notes": data.get("notes"),
        "is_danger": bool(data.get("is_danger")),
        "wrong_medication": bool(data.get("wrong_medication")),
    }


def _analyze_health_intent(message: str, structured_block: str) -> dict:
    # Önce basit kural: "ağrı ... 8" gibi kalıplar LLM olmadan da yakalansın
    pain_match = re.search(r"(?:ağrı|agri).{0,20}?(\d{1,2})", message, re.IGNORECASE)
    rule_pain = None
    if pain_match:
        try:
            rule_pain = max(0, min(10, int(pain_match.group(1))))
        except ValueError:
            rule_pain = None

    try:
        response = _client().chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": DECISION_SYSTEM},
                {
                    "role": "user",
                    "content": f"{structured_block}\nKullanıcı mesajı: {message}",
                },
            ],
            temperature=0.1,
            max_tokens=200,
        )
        decision = _parse_decision(response.choices[0].message.content or "")
    except Exception as error:
        print(f"[HEALTH] karar LLM hatası: {error}")
        decision = {
            "action": "none",
            "medication_name": None,
            "pain_level": rule_pain,
            "mood": None,
            "notes": None,
            "is_danger": False,
            "wrong_medication": False,
        }

    if decision.get("pain_level") is None and rule_pain is not None:
        decision["pain_level"] = rule_pain
        if decision["action"] == "none":
            decision["action"] = "log_health"

    # "içtim" kuralı
    if decision["action"] == "none" and re.search(r"i[cç]tim|ald[ıi]m", message, re.IGNORECASE):
        decision["action"] = "confirm_medication"
        if not decision.get("medication_name"):
            meds = re.findall(r"([A-Za-zÇĞİÖŞÜçğıöşü]{3,})", message)
            # basit: structured listedeki isimlerle eşleşecek şekilde tool tarafı çözer
            decision["medication_name"] = meds[0] if meds else None

    return decision


def health_node(state: AgentState) -> AgentState:
    user_name = state.get("user_name") or "canım"
    user_message = state.get("user_message") or ""
    elder_id = state.get("elder_id") or ""
    conversation_id = state.get("conversation_id") or ""

    memory_block = format_memories_for_prompt(state.get("retrieved_memories") or [])
    structured_block = format_structured_for_prompt(state.get("structured_context"))

    decision = _analyze_health_intent(user_message, structured_block)
    tool_messages: list[str] = []

    if decision["action"] == "confirm_medication":
        med_name = decision.get("medication_name")
        # İsim yoksa listedeki ilk ilacı dene
        if not med_name:
            meds = (state.get("structured_context") or {}).get("todays_medications") or []
            med_name = meds[0]["name"] if meds else None
        result = record_medication_taken(elder_id, med_name or "")
        tool_messages.append(result["message"])
    elif decision["action"] == "log_health":
        result = record_daily_checkin(
            conversation_id=conversation_id,
            mood=str(decision.get("mood") or "Normal"),
            pain_level=decision.get("pain_level"),
            notes=str(decision.get("notes") or ""),
        )
        tool_messages.append(result["message"])

    escalate, reason = should_escalate_health(
        pain_level=decision.get("pain_level"),
        is_danger=bool(decision.get("is_danger")),
        wrong_medication=bool(decision.get("wrong_medication")),
        threshold=HEALTH_PAIN_ESCALATION_THRESHOLD,
    )

    system = (
        f"{HEALTH_STUB_SYSTEM} Kullanıcı adı: {user_name}.\n"
        f"{structured_block}{memory_block}"
        f"Araç sonuçları: {'; '.join(tool_messages) or 'yok'}.\n"
        "İlaç saatlerini uydurma. Teşhis veya doz değişikliği önerme. "
        "Kısa ve sıcak yanıt ver."
    )
    if escalate:
        system += " Durum ciddi olabilir; sakinleştir, yakınların bilgilendirileceğini söyle."

    messages: list[dict] = [{"role": "system", "content": system}]
    for item in (state.get("chat_history") or [])[-4:]:
        role = item.get("role")
        content = item.get("content")
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_message})

    try:
        response = _client().chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=messages,
            max_tokens=160,
            temperature=0.4,
        )
        reply = (response.choices[0].message.content or "").strip()
    except Exception as error:
        print(f"[HEALTH] yanıt hatası: {error}")
        if tool_messages:
            reply = f"{user_name}, {tool_messages[0]}"
        else:
            reply = f"{user_name}, durumunu not ettim. İlaçlarım veya Durumum sekmesinden de bakabilirsin."

    stored = extract_and_store_memories(elder_id, user_message)

    return {
        **state,
        "agent_response": reply,
        "routed_agent": "health",
        "escalation_needed": escalate,
        "escalation_reason": reason if escalate else state.get("escalation_reason"),
        "urgency": "high" if escalate else state.get("urgency") or "low",
        "memories_stored": stored,
        "health_decision": decision,
        "health_tool_results": tool_messages,
    }
