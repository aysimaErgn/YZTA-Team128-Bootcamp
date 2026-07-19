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
from orchestrator.memory.shared import (
    build_shared_from_health_decision,
    format_shared_health_for_prompt,
    parse_mood_label,
    remember_shared_context,
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

# Model yine de ilaç adı kaçırırsa yakala (güvenlik ağı)
_MED_SUGGEST_RE = re.compile(
    r"\b("
    r"parol|parasetamol|acetaminophen|aspirin|aspiri|"
    r"ibuprofen|apro[l]?|aprana[xks]|voltar[e]?n|diklofenak|"
    r"naproksen|arveles|minoset|vermidon|geralgine|"
    r"ağrı\s*kesici|agri\s*kesici|"
    r"(?:şunu|bunu|şu|bu)\s+i[cç]|"
    r"i[cç]melisin|i[cç]ebilirsin|alabilirsin"
    r")\b",
    re.IGNORECASE,
)

_ASK_WHERE_RE = re.compile(
    r"("
    r"ağr[ıi].{0,20}(nerede|nasıl|nerde)|"
    r"nerede\s+ve\s+nasıl|"
    r"nerde\s+ve\s+nas[ıi]l|"
    r"nas[ıi]l\s+ba[sş]lad|"
    r"nerede\s+ba[sş]lad|"
    r"batma,\s*zonklama"
    r")",
    re.IGNORECASE,
)

_ASK_PRIOR_MED_RE = re.compile(
    r"("
    r"daha\s*önce\s*ila[cç]\s*al|"
    r"ila[cç]\s*al[ıi]p\s*almad|"
    r"bug[uü]n.{0,20}ila[cç].{0,20}(ald[ıi]n|almad)|"
    r"ila[cç]\s*al[ıi]p\s*almad[ıi][gğ][ıi]n[ıi]z[ıi]"
    r")",
    re.IGNORECASE,
)


def _looks_like_pain_complaint(message: str) -> bool:
    return bool(
        re.search(r"ağr[ıi]|agri|sız[ıi]|aci|acı|zonkla|bat[ıi]yor", message or "", re.I)
    )


def _asks_for_medication(message: str) -> bool:
    text = message or ""
    return bool(
        re.search(
            r"hangi\s+ila[cç]|ne\s+i[cç](eyim|meliyim)|ila[cç]\s*(öner|ver)|"
            r"ne\s+alay[ıi]m|ağrı\s*kesici\s*(ver|öner)",
            text,
            re.IGNORECASE,
        )
    )


def extract_pain_slots(message: str) -> dict[str, str | bool | None]:
    """Kullanıcı mesajından bilinen ağrı alanlarını çıkar (tekrar soruyu engelle)."""
    text = message or ""
    location = None
    if re.search(r"al[nıi]n|alnim|alın", text, re.I):
        location = "alnın ortası / alın"
    elif re.search(r"\b(bel|sırt|sirt|diz|ense|şaka[k]|şakak|kar[ıi]n|göğüs|gogus)\b", text, re.I):
        m = re.search(r"\b(bel|sırt|sirt|diz|ense|şaka[k]|şakak|kar[ıi]n|göğüs|gogus)\b", text, re.I)
        location = m.group(1) if m else None
    elif re.search(r"ba[sş].{0,12}ağr|bas.{0,12}agr", text, re.I):
        location = "baş"

    quality = None
    if re.search(r"zonkla", text, re.I):
        quality = "zonklama"
    elif re.search(r"bat[ıi]yor|batma", text, re.I):
        quality = "batma"
    elif re.search(r"yan(ma|ıyor|iyor)", text, re.I):
        quality = "yanma"
    elif re.search(r"k[uü]nt|s[ıi]z[ıi]", text, re.I):
        quality = "künt/sızı"

    duration = None
    if re.search(r"sabah(tan)?\s*beri|sabahtan", text, re.I):
        duration = "sabahtan beri"
    elif re.search(r"(d[uü]nden|ak[sş]amdan)\s*beri", text, re.I):
        duration = "bir süredir"
    elif re.search(r"(saat|g[uü]n|dakika).{0,8}beri|\b(yeni|az\s*önce)\b", text, re.I):
        duration = "belirttiği süredir"

    level = None
    m_level = re.search(r"(?:ağrı|agri).{0,20}?(\d{1,2})", text, re.I)
    if m_level:
        try:
            level = str(max(0, min(10, int(m_level.group(1)))))
        except ValueError:
            level = None

    took_med = None
    med_taken_name = None
    hours_ago = None

    hm = re.search(r"(\d+)\s*saat\s*(?:önce|once)", text, re.IGNORECASE)
    if hm:
        hours_ago = hm.group(1)

    named = re.search(
        r"([A-Za-zÇĞİÖŞÜçğıöşü]{4,})\s+(?:ila[cç][ıi]\s+)?(?:i[cç]tim|i[cç]miştim|icmistim|ald[ıi]m)",
        text,
        re.IGNORECASE,
    )
    if named:
        candidate = named.group(1)
        if candidate.lower() not in {
            "önce",
            "once",
            "biraz",
            "sabah",
            "hangi",
            "şimdi",
            "simdi",
            "daha",
            "saat",
            "dolayı",
        }:
            med_taken_name = candidate

    if re.search(
        r"(ila[cç]|hap|[A-Za-zÇĞİÖŞÜçğıöşü]{4,}).{0,40}"
        r"(i[cç]tim|i[cç]miştim|icmistim|ald[ıi]m|alm[ıi][sş]t[ıi]m)",
        text,
        re.IGNORECASE,
    ):
        took_med = True

    if re.search(r"(hen[uü]z|daha)\s*(ila[cç]|hap).{0,12}(i[cç]medim|almad[ıi]m)", text, re.I):
        took_med = False

    if re.search(r"geçmedi|gecmedi", text, re.I) and (
        med_taken_name or re.search(r"ila[cç]|hap|i[cç]miştim|i[cç]tim", text, re.I)
    ):
        took_med = True

    return {
        "location": location,
        "quality": quality,
        "duration": duration,
        "level": level,
        "took_med": took_med,
        "med_taken_name": med_taken_name,
        "hours_ago": hours_ago,
        "asks_medication": _asks_for_medication(text),
        "is_pain": _looks_like_pain_complaint(text),
    }


def _known_summary(slots: dict) -> str:
    bits = []
    if slots.get("location"):
        bits.append(slots["location"])
    if slots.get("quality"):
        bits.append(slots["quality"])
    if slots.get("duration"):
        bits.append(slots["duration"])
    if slots.get("level"):
        bits.append(f"şiddet {slots['level']}/10")
    if slots.get("took_med") is True:
        med = slots.get("med_taken_name") or "bir ilaç"
        when = f"{slots['hours_ago']} saat önce " if slots.get("hours_ago") else ""
        bits.append(f"{when}{med} almış, geçmemiş")
    return ", ".join(bits)


def _missing_pain_questions(slots: dict) -> list[str]:
    missing = []
    if not slots.get("location") or not slots.get("quality"):
        if not slots.get("location") and not slots.get("quality"):
            missing.append("ağrının yeri ve nasıl olduğu (batma, zonklama, yanma)")
        elif not slots.get("location"):
            missing.append("ağrının tam yeri")
        elif not slots.get("quality"):
            missing.append("ağrının nasıl olduğu (batma, zonklama, yanma)")
    if not slots.get("duration"):
        missing.append("ne zamandır sürdüğü")
    # İlaç aldığı zaten belliyse tekrar sorma
    if slots.get("took_med") is None:
        missing.append("bugün daha önce ilaç alıp almadığı")
    return missing


def build_health_turn_guidance(user_message: str) -> str:
    """Prompt'a eklenecek: bilinenler / eksikler / ilaç talebi."""
    slots = extract_pain_slots(user_message)
    if not slots.get("is_pain") and not slots.get("asks_medication"):
        return (
            "Bu turda gereksiz soru sorma. Kullanıcıyı dinle; "
            "ilaç veya teşhis önerme."
        )

    known = _known_summary(slots)
    missing = _missing_pain_questions(slots)
    lines = ["Bu tur için talimat:"]
    lines.append(
        "- Önce ilgili ve empatik ol; soğuk soru listesi gibi konuşma. "
        "Kullanıcının anlattığına 'anlıyorum / zor olmalı' ile karşılık ver."
    )
    if known:
        lines.append(
            f"- Kullanıcı ZATEN söyledi (tekrar SORMA, önce sıcakça özetle/onayla): {known}."
        )
    if missing:
        lines.append(
            "- En fazla BİR eksik soru sor (nazikçe): " + missing[0] + "."
        )
    else:
        lines.append(
            "- Yer/tip/süre biliniyor. 'Nerede/nasıl' sorma. "
            "Kısa onay + ilgi göster; gerekirse sadece bugün ilaç alıp almadığını sor."
        )
    if slots.get("asks_medication"):
        lines.append(
            "- İlaç istiyor: reddet ama sıcak kal; ilaç adı / ikinci doz önerme. "
            "İlaçlarım / doktor / aile. Yalnız bırakma."
        )
    if slots.get("took_med") is True:
        lines.append(
            "- Kullanıcı ZATEN ilaç aldığını söyledi; "
            "'bugün ilaç aldın mı?' diye ASLA tekrar sorma. Aldığını onayla, geçmediğini anladığını söyle."
        )
    return "\n".join(lines)


def _safe_contextual_reply(user_name: str, user_message: str) -> str:
    slots = extract_pain_slots(user_message)
    known = _known_summary(slots)
    missing = _missing_pain_questions(slots)

    if known:
        parts = [
            f"{user_name}, seni duyuyorum; böyle bir ağrı gerçekten yorucu olabilir.",
            f"Anlattığın kadarıyla {known} — bunu not ettim.",
        ]
    elif slots.get("is_pain"):
        parts = [
            f"{user_name}, seni duyuyorum; yanında olduğumu bil.",
            "Rahatsızlığın için üzgünüm.",
        ]
    else:
        parts = [f"{user_name}, seni dinliyorum; halini önemsiyorum."]

    if slots.get("took_med") is True:
        med = slots.get("med_taken_name") or "aldığın ilaç"
        parts.append(
            f"{med} sonrası geçmemesi can sıkıcı; bir doz daha veya yeni ilaç önermem doğru olmaz."
        )

    if slots.get("asks_medication"):
        parts.append(
            "Hangi ilacı şimdi içmen gerektiğini ben söyleyemem; üst üste ilaç zarar verebilir."
        )
        parts.append(
            "Kayıtlı ilaçların için İlaçlarım sekmesine bak; "
            "ağrı sürüyorsa bir yakınına veya doktoruna danışmanı isterim."
        )
        parts.append("İstersen yanında dinlerim; yalnız değilsin.")
        return " ".join(parts)

    if missing:
        q = missing[0]
        if "ilaç" in q:
            parts.append("Merak ettim, bugün bu şikayet için daha önce bir ilaç aldın mı?")
        elif "yer" in q or "nasıl" in q:
            parts.append(
                "İlaç önermiyorum; biraz daha anlatır mısın, ağrı nerede ve nasıl — "
                "batma, zonklama gibi mi?"
            )
        else:
            parts.append(f"İlaç önermiyorum; {q} söylersen daha iyi anlayabilirim.")
    else:
        parts.append(
            "İlaç önermiyorum. Dinlenmen iyi olabilir; "
            "şikayet artarsa veya yeni belirtiler olursa yakınlarına haber ver."
        )
    parts.append("Yanındayım; anlatmak istediğin başka bir şey var mı?")
    return " ".join(parts)


def _safe_pain_clarifying_reply(user_name: str, user_message: str = "") -> str:
    if user_message:
        return _safe_contextual_reply(user_name, user_message)
    return (
        f"{user_name}, seni duyuyorum. İlaç önermiyorum; önce birlikte netleştirelim. "
        "Ağrı nerede ve nasıl — batma, zonklama, yanma mı? "
        "Ne zamandır var ve bugün daha önce ilaç aldın mı?"
    )


def _repeats_answered_questions(reply: str, user_message: str) -> bool:
    """Bilinen yer/tip veya ilaç alımı varken aynı soruyu yapıştırırsa yakala."""
    slots = extract_pain_slots(user_message)
    text = reply or ""
    if slots.get("location") and slots.get("quality") and _ASK_WHERE_RE.search(text):
        return True
    if slots.get("took_med") is True and _ASK_PRIOR_MED_RE.search(text):
        return True
    return False


def _sanitize_health_reply(reply: str, user_name: str, user_message: str) -> str:
    text = (reply or "").strip()
    if not text:
        return _safe_contextual_reply(user_name, user_message)

    if _MED_SUGGEST_RE.search(text):
        print("[HEALTH] İlaç önerisi filtrelendi.")
        return _safe_contextual_reply(user_name, user_message)

    if _repeats_answered_questions(text, user_message):
        print("[HEALTH] Tekrarlayan netleştirme sorusu filtrelendi.")
        return _safe_contextual_reply(user_name, user_message)

    return text

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

    if rule_pain is not None and decision.get("pain_level") is None:
        decision["pain_level"] = rule_pain

    # Ağrı yakalandıysa check-in yaz (LLM action=none bıraksa bile)
    if decision.get("pain_level") is not None and decision.get("action") == "none":
        decision["action"] = "log_health"
        if not decision.get("mood"):
            if re.search(r"halsiz|yorgun|k[oö]t[uü]", message, re.IGNORECASE):
                decision["mood"] = "Halsiz"
            else:
                decision["mood"] = "Normal"

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
    shared_block = format_shared_health_for_prompt(state)

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
            elder_id=elder_id or None,
        )
        tool_messages.append(result["message"])

    escalate, reason = should_escalate_health(
        pain_level=decision.get("pain_level"),
        is_danger=bool(decision.get("is_danger")),
        wrong_medication=bool(decision.get("wrong_medication")),
        threshold=HEALTH_PAIN_ESCALATION_THRESHOLD,
    )

    turn_guidance = build_health_turn_guidance(user_message)
    system = (
        f"{HEALTH_STUB_SYSTEM}\nKullanıcı adı: {user_name}.\n"
        f"{structured_block}{memory_block}{shared_block}"
        f"{turn_guidance}\n"
        f"Araç sonuçları: {'; '.join(tool_messages) or 'yok'}.\n"
        "İlaç adı uydurma veya önerme. Teşhis koyma. "
        "Bilinen bilgileri tekrar sorma. Önce empati ve özet, sonra en fazla bir soru. "
        "İlgili ve sıcak ol. Kısa yanıt ver."
    )
    if escalate:
        system += " Durum ciddi olabilir; sakinleştir, yakınların bilgilendirileceğini söyle; ilaç önerme."

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
            max_tokens=180,
            temperature=0.25,
        )
        reply = _sanitize_health_reply(
            (response.choices[0].message.content or "").strip(),
            user_name,
            user_message,
        )
    except Exception as error:
        print(f"[HEALTH] yanıt hatası: {error}")
        if _looks_like_pain_complaint(user_message) or _asks_for_medication(user_message):
            reply = _safe_contextual_reply(user_name, user_message)
        elif tool_messages:
            reply = f"{user_name}, {tool_messages[0]}"
        else:
            reply = (
                f"{user_name}, durumunu not ettim. "
                "İlaç önermiyorum; İlaçlarım veya Durumum sekmesinden de bakabilirsin."
            )

    stored = extract_and_store_memories(elder_id, user_message)

    shared = build_shared_from_health_decision(
        decision,
        previous=state.get("shared_health_context"),
        tool_ok=bool(tool_messages),
    )
    mood = parse_mood_label(str(decision.get("mood") or shared.get("detected_mood") or "Nötr"))
    remember_shared_context(conversation_id, shared, mood)

    return {
        **state,
        "agent_response": reply,
        "routed_agent": "health",
        "active_agent": "health",
        "escalation_needed": escalate,
        "escalation_reason": reason if escalate else state.get("escalation_reason"),
        "urgency": "high" if escalate else state.get("urgency") or "low",
        "memories_stored": stored,
        "health_decision": decision,
        "health_tool_results": tool_messages,
        "shared_health_context": shared,
        "detected_mood": mood,
    }
