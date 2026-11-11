import app.retrieval.hybrid as hybrid
from app.retrieval.hybrid import BM25Scope, HybridRetriever, rrf, tokenize
from app.retrieval.vector import Hit


def hit(i, text, page=1):
    return Hit(i, "tcs", 2025, page, None, text, 0.0)


def test_tokenize_joins_indian_digit_groups_and_drops_stopwords():
    assert tokenize("What was the Revenue from operations: 2,55,324?") == [
        "revenue",
        "operations",
        "255324",
    ]
    assert tokenize("EBIT margin 24.3%") == ["ebit", "margin", "24.3"]


def test_rrf_rewards_items_ranked_well_in_both_lists():
    # 2 is 2nd in both lists; 1 and 3 are 1st in one list and absent from the other.
    assert rrf([[1, 2], [3, 2]])[0] == 2


def test_bm25_finds_exact_terms():
    scope = BM25Scope(
        [
            hit(1, "Our people strategy focuses on learning"),
            hit(2, "Turnover rate for permanent employees: attrition 13.3%"),
            hit(3, "Revenue from operations 2,55,324"),
        ]
    )
    assert [h.chunk_id for h in scope.top("employee attrition rate", 3)][0] == 2
    assert [h.chunk_id for h in scope.top("revenue 2,55,324", 3)][0] == 3
    assert scope.top("zebra", 3) == []  # no matching term -> nothing, not random chunks


class FakeReranker:
    """Scores a chunk by how often it says 'consolidated'."""

    def scores(self, question, texts):
        return [t.lower().count("consolidated") for t in texts]


def test_hybrid_fuses_both_lists_then_reranks(monkeypatch):
    vec_hits = [hit(1, "standalone revenue"), hit(2, "consolidated revenue consolidated")]
    kw_hits = [hit(3, "consolidated revenue"), hit(1, "standalone revenue")]
    monkeypatch.setattr(hybrid, "search", lambda *a, **k: vec_hits)
    r = HybridRetriever(session=None, embed=lambda texts: [[0.0]], reranker=FakeReranker())
    r._scope = lambda c, y: type("S", (), {"top": lambda self, q, n: kw_hits})()

    got = r("TCS revenue FY2025", k=2)
    assert [h.chunk_id for h in got] == [2, 3]  # reranked by the fake scorer
    assert got[0].distance == -2  # lower is better

    no_rerank = HybridRetriever(session=None, embed=lambda texts: [[0.0]])
    no_rerank._scope = r._scope
    assert [h.chunk_id for h in no_rerank("TCS revenue FY2025", k=3)][0] == 1  # in both lists
