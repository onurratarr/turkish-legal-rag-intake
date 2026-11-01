import pytest

from legal_rag.review import ReviewQueue


@pytest.fixture
def q():
    return ReviewQueue()


def test_nothing_released_until_reviewed(q):
    q.submit("answer", {"question": "q", "text": "draft"})
    assert q.released() == [] and len(q.pending()) == 1


def test_approve_with_rubric(q):
    i = q.submit("answer", {"question": "q", "text": "draft"})
    r = q.approve(i, "Av. Demo", rubric={"accuracy": 2, "grounding": 2, "citation": 1})
    assert r["status"] == "approved" and r["final_payload"]["text"] == "draft" and r["rubric"]["citation"] == 1
    assert [x["id"] for x in q.released()] == [i]


def test_edit_keeps_original_and_final(q):
    i = q.submit("answer", {"question": "q", "text": "draft"})
    r = q.edit(i, "Av. Demo", {"text": "corrected"})
    assert r["payload"]["text"] == "draft" and r["final_payload"]["text"] == "corrected"


def test_reject_requires_note_and_is_not_released(q):
    i = q.submit("intake", {"summary": "s"})
    with pytest.raises(ValueError):
        q.reject(i, "Av. Demo", "")
    q.reject(i, "Av. Demo", "conflict of interest")
    assert q.released() == []


def test_cannot_review_twice_or_anonymously(q):
    i = q.submit("answer", {"text": "x"})
    with pytest.raises(ValueError):
        q.approve(i, "")
    q.approve(i, "Av. Demo")
    with pytest.raises(ValueError):
        q.reject(i, "Av. Demo", "late")


def test_invalid_rubric_rejected(q):
    i = q.submit("answer", {"text": "x"})
    with pytest.raises(ValueError):
        q.approve(i, "Av. Demo", rubric={"accuracy": 5})
