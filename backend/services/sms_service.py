"""Twilio SMS — FAMILY_SMS_ENABLED=true ise gerçek, değilse güvenli stub."""

from __future__ import annotations

import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

SMS_PAIN_ESCALATION_THRESHOLD = int(os.getenv("SMS_PAIN_ESCALATION_THRESHOLD", "9"))


def should_send_family_sms(
    *,
    pain_level: int | None = None,
    is_danger: bool = False,
    wrong_medication: bool = False,
    intent: str | None = None,
    urgency: str | None = None,
) -> bool:
    """
    SMS barajı (yanlış pozitif azaltma):
    - ağrı >= 9 → SMS
    - is_danger / yanlış ilaç → SMS
    - ağrı biliniyor ve < 9 → SMS YOK (WS eskalasyonu yeterli; örn. 7)
    - ağrı yok + intent=escalation + urgency=high → SMS (düşme, nefes vb.)
    """
    if is_danger or wrong_medication:
        return True

    if pain_level is not None:
        try:
            return int(pain_level) >= SMS_PAIN_ESCALATION_THRESHOLD
        except (TypeError, ValueError):
            return False

    if (intent or "").lower() == "escalation" and (urgency or "").lower() == "high":
        return True

    return False


def send_family_sms(to_phone: str, message: str) -> bool:
    """FAMILY_SMS_ENABLED=true ise Twilio, aksi halde [SMS STUB] log."""
    if not to_phone or not str(to_phone).strip():
        logger.warning("SMS gönderilemedi: alıcı telefon yok.")
        return False

    phone = str(to_phone).strip()
    body = (message or "").strip()
    if not body:
        logger.warning("SMS gönderilemedi: mesaj boş.")
        return False

    sms_enabled = os.getenv("FAMILY_SMS_ENABLED", "false").lower() in {"1", "true", "yes", "on"}

    if not sms_enabled:
        logger.info("[SMS STUB] Kime: %s | Mesaj: %s", phone, body)
        print(f"[SMS STUB] Kime: {phone} | Mesaj: {body}")
        return True

    try:
        from twilio.rest import Client
    except ImportError:
        logger.error("twilio paketi yüklü değil; SMS gönderilemedi.")
        return False

    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    from_phone = os.getenv("TWILIO_PHONE_NUMBER")

    if not all([account_sid, auth_token, from_phone]):
        logger.error("Twilio kimlik bilgileri eksik (SID/TOKEN/PHONE).")
        return False

    try:
        client = Client(account_sid, auth_token)
        client.messages.create(body=body, from_=from_phone, to=phone)
        logger.info("SMS gönderildi → %s", phone)
        return True
    except Exception as error:
        logger.error("Twilio SMS hatası: %s", error)
        return False


def _user_id_from_elder_notes(notes: str | None) -> str | None:
    if not notes:
        return None
    match = re.search(r"users tablosu user_id:\s*([^\s]+)", notes, re.IGNORECASE)
    return match.group(1).strip() if match else None


def resolve_family_contact(
    *,
    user_id: str | None = None,
    elder_id: str | None = None,
) -> dict[str, Any]:
    """
    Aile telefonu: users.family_phone.
    İsteğe bağlı users.family_sms_enabled (yoksa True).
    Demo: FAMILY_SMS_OVERRIDE_PHONE env.
    """
    override = (os.getenv("FAMILY_SMS_OVERRIDE_PHONE") or "").strip()
    if override:
        return {"phone": override, "sms_enabled": True, "source": "env_override"}

    try:
        from database import supabase
    except Exception as error:
        logger.warning("Supabase yok; aile telefonu çözülemedi: %s", error)
        return {"phone": None, "sms_enabled": False, "source": "error"}

    candidate_ids: list[str] = []
    if user_id:
        candidate_ids.append(str(user_id))
    if elder_id and str(elder_id) not in candidate_ids:
        candidate_ids.append(str(elder_id))
        try:
            elder_res = (
                supabase.table("elders")
                .select("id, notes")
                .eq("id", elder_id)
                .limit(1)
                .execute()
            )
            if elder_res.data:
                linked = _user_id_from_elder_notes(elder_res.data[0].get("notes"))
                if linked and linked not in candidate_ids:
                    candidate_ids.append(linked)
        except Exception as error:
            logger.warning("Elder notes okunamadı: %s", error)

    for candidate in candidate_ids:
        try:
            # family_sms_enabled kolonu olmayabilir — önce geniş select dene
            try:
                res = (
                    supabase.table("users")
                    .select("id, family_phone, family_sms_enabled, family_name")
                    .eq("id", candidate)
                    .limit(1)
                    .execute()
                )
            except Exception:
                res = (
                    supabase.table("users")
                    .select("id, family_phone, family_name")
                    .eq("id", candidate)
                    .limit(1)
                    .execute()
                )

            if not res.data:
                continue
            row = res.data[0]
            phone = (row.get("family_phone") or "").strip()
            if not phone:
                continue
            sms_pref = row.get("family_sms_enabled")
            sms_enabled = True if sms_pref is None else bool(sms_pref)
            return {
                "phone": phone,
                "sms_enabled": sms_enabled,
                "family_name": row.get("family_name"),
                "source": f"users:{candidate}",
            }
        except Exception as error:
            logger.warning("users telefon sorgusu başarısız (%s): %s", candidate, error)

    return {"phone": None, "sms_enabled": False, "source": "not_found"}


def maybe_notify_family_sms(state: dict[str, Any]) -> dict[str, Any]:
    """Eskalasyon state'inden SMS kararı + gönderim. Sonuç özeti döner."""
    decision = state.get("health_decision") or {}
    pain_level = decision.get("pain_level")
    if pain_level is None and state.get("pain_level") is not None:
        pain_level = state.get("pain_level")

    is_danger = bool(decision.get("is_danger") or state.get("is_danger"))
    wrong_medication = bool(decision.get("wrong_medication"))
    intent = state.get("intent")
    urgency = state.get("urgency") or "high"

    if not should_send_family_sms(
        pain_level=pain_level if pain_level is not None else None,
        is_danger=is_danger,
        wrong_medication=wrong_medication,
        intent=intent,
        urgency=urgency,
    ):
        return {"attempted": False, "sent": False, "reason": "below_sms_threshold"}

    contact = resolve_family_contact(
        user_id=state.get("user_id"),
        elder_id=state.get("elder_id"),
    )
    phone = contact.get("phone")
    if not phone:
        return {"attempted": True, "sent": False, "reason": "no_family_phone"}

    if contact.get("sms_enabled") is False:
        return {"attempted": True, "sent": False, "reason": "family_sms_disabled"}

    detail = state.get("escalation_reason") or state.get("user_message") or "Kritik sağlık olayı"
    elder_name = state.get("user_name") or "Yakınınız"
    body = (
        f"Yanımda Al KRİTİK UYARI: {elder_name} için yüksek risk.\n"
        f"Detay: {str(detail)[:160]}\n"
        "Lütfen aile panelini kontrol edin."
    )
    sent = send_family_sms(phone, body)
    return {
        "attempted": True,
        "sent": sent,
        "reason": "sent" if sent else "send_failed",
        "phone_masked": _mask_phone(phone),
    }


def _mask_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 4:
        return "***"
    return f"***{digits[-4:]}"
