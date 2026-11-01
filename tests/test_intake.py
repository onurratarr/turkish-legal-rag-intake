import json

from legal_rag.intake import IntakeAgent, rule_based_intake, validate_intake

SLOTS = ["2026-11-03T10:00", "2026-11-04T11:00", "2026-11-05T09:30"]


def test_employment_intake_fields():
    d = rule_based_intake("Merhaba, adım Ayşe Yılmaz. İşten çıkarıldım, kıdem tazminatı ödenmedi. "
                          "Telefon: 0532 000 00 00, e-posta ayse@example.com. 12.10.2026 tarihinde çıkarıldım.", SLOTS)
    assert d["client_name"] == "Ayşe Yılmaz"
    assert d["phone"] == "05320000000" and d["email"] == "ayse@example.com"
    assert d["matter_type"] == "employment" and d["key_dates"] == ["12.10.2026"]
    assert d["missing_fields"] == [] and d["conflict_check_required"] is True
    assert validate_intake(d) == []


def test_urgency_picks_earliest_slot():
    urgent = rule_based_intake("Ev sahibim tahliye için tebligat gönderdi, acil yardım lazım.", SLOTS)
    normal = rule_based_intake("Kiracım depozito konusunda soru sordu.", SLOTS)
    assert urgent["matter_type"] == "tenancy" and urgent["urgency"] == "high"
    assert urgent["proposed_consultation"] == SLOTS[0]
    assert normal["urgency"] == "normal" and normal["proposed_consultation"] == SLOTS[2]


def test_missing_contact_and_other_matter():
    d = rule_based_intake("Bir konuda danışmak istiyorum.", SLOTS)
    assert d["matter_type"] == "other"
    assert {"client_name", "phone", "contact"} <= set(d["missing_fields"])


def test_amounts_parsed():
    assert rule_based_intake("Satıcı 12.500 TL iade etmedi, ürün ayıplı.", SLOTS)["amounts_try"] == [12500]


def test_validate_catches_bad_schema():
    errs = validate_intake({"matter_type": "space-law", "urgency": "whenever"})
    assert "enum:matter_type" in errs and "enum:urgency" in errs and "missing:summary" in errs


def test_llm_intake_invalid_output_falls_back():
    agent = IntakeAgent("openai", post=lambda p: {"choices": [{"message": {"content": json.dumps({"matter_type": "x"})}}]},
                        slots=SLOTS)
    d = agent.run("Boşanma davası açmak istiyorum, adım Ali Veli.")
    assert d["source"] == "rule_based_fallback" and d["matter_type"] == "family"


def test_llm_intake_valid_output_used():
    good = rule_based_intake("Miras konusunda yardım istiyorum, adım Ali Veli.", SLOTS) | {"summary": "LLM summary"}
    agent = IntakeAgent("openai", post=lambda p: {"choices": [{"message": {"content": json.dumps(good)}}]}, slots=SLOTS)
    d = agent.run("Miras konusunda yardım istiyorum, adım Ali Veli.")
    assert d["source"] == "llm" and d["summary"] == "LLM summary" and d["conflict_check_required"] is True
