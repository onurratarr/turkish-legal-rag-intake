from legal_rag.answer import Answer
from legal_rag.corpus import load_corpus
from legal_rag.evaluate import grounding_score, run_eval, score, to_markdown

BY_ID = {c.cite_id: c for c in load_corpus()}


def test_grounding_detects_unsupported_sentence():
    good = "Kiracı belirsiz süreli sözleşmeyi 30 gün önceden yazılı bildirimle feshedebilir [SYN-KIRA-01 m.2]."
    bad = good + " Fesih için noter onayı ve harç ödemesi zorunludur [SYN-KIRA-01 m.2]."
    assert grounding_score(good, BY_ID) == 1.0
    assert grounding_score(bad, BY_ID) == 0.5
    assert grounding_score("Kiracı 30 gün önceden yazılı bildirim yapar.", BY_ID) == 0.0  # uncited


def test_score_wrong_citation_and_incomplete():
    item = {"id": "t", "expected_citations": ["SYN-KIRA-01 m.2"], "must_include": ["30 gün", "yazılı"], "answerable": True}
    text = "Kiracı belirsiz süreli sözleşmeyi bildirimle feshedebilir [SYN-KIRA-01 m.4]."
    r = score(Answer("q", text, ["SYN-KIRA-01 m.4"], [], False), item, BY_ID)
    assert r["citation_precision"] == 0.0 and r["completeness"] == 0.0 and r["passed"] is False


def test_unanswerable_must_abstain():
    item = {"id": "u", "expected_citations": [], "must_include": [], "answerable": False}
    assert score(Answer("q", "x", [], [], True), item, BY_ID)["passed"] is True
    assert score(Answer("q", "x [SYN-IS-01 m.1]", ["SYN-IS-01 m.1"], [], False), item, BY_ID)["passed"] is False


def test_eval_regression_floor():
    """Guard against retrieval regressions on the synthetic set (floors, not targets)."""
    res = run_eval()
    s = res["summary"]
    assert s["n"] == 12
    assert s["abstention_accuracy"] == 1.0
    assert s["citation_recall"] >= 0.9 and s["completeness"] >= 0.9
    assert "synthetic data" in to_markdown(res)
