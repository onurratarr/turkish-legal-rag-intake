from legal_rag.answer import DISCLAIMER, LegalAssistant, MockAnswerer, OpenAICompatibleAnswerer, extract_citations
from legal_rag.corpus import load_corpus
from legal_rag.retrieval import BM25Retriever
from legal_rag.text import content_stems, expand_query, normalize

CHUNKS = load_corpus()
RET = BM25Retriever(CHUNKS)


def test_corpus_is_all_synthetic_and_citable():
    assert len(CHUNKS) >= 15
    assert all(c.source_type == "synthetic" for c in CHUNKS)
    assert len({c.cite_id for c in CHUNKS}) == len(CHUNKS)


def test_turkish_normalisation_and_stemming():
    assert normalize("İŞÇİ Kıdem") == "isci kidem"
    assert content_stems("tazminatımı") == content_stems("tazminatı")  # first-5-char stemming handles suffixes


def test_synonym_expansion():
    assert "kiraya veren" in expand_query("Ev sahibi depozitoyu vermiyor")


def test_bm25_top_hit():
    assert RET.search("Mirası reddetme süresi ne kadar?")[0].chunk.cite_id == "SYN-MIRAS-01 m.1"
    assert RET.search("fazla mesai ücreti")[0].chunk.cite_id == "SYN-IS-01 m.3"


def test_answer_has_valid_citations_and_disclaimer():
    a = LegalAssistant(RET, MockAnswerer()).ask("Kıdem tazminatı nasıl hesaplanır?")
    assert not a.abstained and "SYN-IS-01 m.2" in a.citations
    assert a.invalid_citations == [] and DISCLAIMER in a.text


def test_abstains_when_corpus_has_no_answer():
    a = LegalAssistant(RET, MockAnswerer()).ask("Trafik cezasına itiraz süresi nedir?")
    assert a.abstained and a.citations == []


def test_llm_backend_hallucinated_citation_is_flagged():
    fake = OpenAICompatibleAnswerer(post=lambda p: {"choices": [{"message": {"content":
        "Fesih bildirimi 30 gün önceden yazılı yapılır [SYN-KIRA-01 m.2]. Ayrıca noter şarttır [SYN-KIRA-01 m.9]."}}]})
    a = LegalAssistant(RET, fake).ask("Kiracı fesih bildirimini kaç gün önceden yapmalı?")
    assert a.invalid_citations == ["SYN-KIRA-01 m.9"]


def test_llm_backend_can_abstain():
    fake = OpenAICompatibleAnswerer(post=lambda p: {"choices": [{"message": {"content": "YETERSIZ_KAYNAK"}}]})
    assert LegalAssistant(RET, fake).ask("Kıdem tazminatı nasıl hesaplanır?").abstained


def test_extract_citations_dedupes():
    assert extract_citations("a [SYN-IS-01 m.1] b [SYN-IS-01 m.1] [SYN-KARAR-01 b.2]") == ["SYN-IS-01 m.1", "SYN-KARAR-01 b.2"]
