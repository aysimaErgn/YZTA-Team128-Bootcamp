"""Sağlık ajanı — ilaç önermeme + bilinen ağrı bilgisini tekrar sormama."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from orchestrator.nodes.health import (
    _repeats_answered_questions,
    _safe_contextual_reply,
    _sanitize_health_reply,
    extract_pain_slots,
)


SAMPLE = (
    "Biraz halsizim, baş ağrım var, ağrı seviyem 5. "
    "alnımın ortasında zonklama şeklinde sabahtan beri var. "
    "hangi ilacı içmeliyim"
)

SAMPLE_TOOK_MED = (
    "Biraz halsizim, baş ağrım var, ağrı seviyem 5. "
    "alnımın ortasında zonklama şeklinde sabahtan beri var. "
    "2 saat önce bir dolorex ilacı içmiştim geçmedi ağrı. "
    "şimdi hangi ilacı içsem geçer"
)


def test_extracts_known_pain_slots():
    slots = extract_pain_slots(SAMPLE)
    assert slots["location"]
    assert slots["quality"] == "zonklama"
    assert slots["duration"]
    assert slots["level"] == "5"
    assert slots["asks_medication"] is True


def test_extracts_prior_medication():
    slots = extract_pain_slots(SAMPLE_TOOK_MED)
    assert slots["took_med"] is True
    assert slots["med_taken_name"]
    assert "dolorex" in slots["med_taken_name"].lower()
    assert slots["hours_ago"] == "2"
    from orchestrator.nodes.health import _missing_pain_questions

    missing = _missing_pain_questions(slots)
    assert not any("ilaç alıp almadığı" in m for m in missing)


def test_contextual_reply_does_not_reask_where():
    out = _safe_contextual_reply("Ayşe", SAMPLE)
    low = out.lower()
    assert "nerede ve nasıl" not in low
    assert "zonklama" in low or "alın" in low or "aln" in low
    assert "yorucu" in low or "duyuyorum" in low or "yanında" in low or "üzgün" in low
    assert "önermem" in low or "önermiyorum" in low or "söyleyemem" in low


def test_contextual_reply_acknowledges_dolorex_no_reask():
    out = _safe_contextual_reply("Ayşe", SAMPLE_TOOK_MED)
    low = out.lower()
    assert "dolorex" in low or "almış" in low
    assert "alıp almad" not in low
    assert "söyleyemem" in low or "önermem" in low or "doğru olmaz" in low


def test_sanitize_replaces_repeating_med_question():
    bad = (
        "Anlıyorum, baş ağrınız zor olmalı. "
        "Bugün daha önce ilaç alıp almadığınızı biliyor musunuz?"
    )
    assert _repeats_answered_questions(bad, SAMPLE_TOOK_MED) is True
    out = _sanitize_health_reply(bad, "Ayşe", SAMPLE_TOOK_MED)
    assert "alıp almad" not in out.lower()


def test_sanitize_replaces_repeating_where_question():
    bad = (
        "Ağrı nerede ve nasıl? (batma, zonklama, yanma, sürekli/aralıklı)\n"
        "Ağrı alnının ortasında zonklama şeklinde."
    )
    assert _repeats_answered_questions(bad, SAMPLE) is True
    out = _sanitize_health_reply(bad, "Ayşe", SAMPLE)
    assert "nerede ve nasıl" not in out.lower()


def test_blocks_parol_suggestion():
    out = _sanitize_health_reply(
        "Bir Parol içebilirsin, geçer.",
        "Ayşe",
        "Başım ağrıyor",
    )
    assert "Parol" not in out


if __name__ == "__main__":
    test_extracts_known_pain_slots()
    test_extracts_prior_medication()
    test_contextual_reply_does_not_reask_where()
    test_contextual_reply_acknowledges_dolorex_no_reask()
    test_sanitize_replaces_repeating_med_question()
    test_sanitize_replaces_repeating_where_question()
    test_blocks_parol_suggestion()
    print("OK — health contextual safety tests passed")
