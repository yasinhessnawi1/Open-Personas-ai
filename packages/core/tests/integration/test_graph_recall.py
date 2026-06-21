"""The turbovec recall gate (Spec K0, T7 / D-K0-7 / criterion 10) — CI-gated.

Promotes the Phase-2 recall spike to a standing test: at the real operating point
(bge-small 384-dim, 4-bit), the turbovec adapter's search — which does ANN then
the MANDATORY exact-rerank — must hit **recall@10 ≥ 0.95** against a float32
brute-force baseline. This is the test that justifies 4-bit (the precision is
recovered at the final ranking). Marked ``external`` (needs the ``[turbovec]``
extra + the sentence-transformers model); runs in the external CI tier, skips
otherwise. Corpus ≥ 1000 so TQ+ calibration is active (not the cold-start identity
fallback, research §5).
"""

from __future__ import annotations

import math

import pytest

pytestmark = pytest.mark.external

_RECALL_BAR = 0.95
_N_CORPUS = 1100  # ≥ TQ+ 1000-sample calibration floor
_N_QUERY = 100
_K = 10

_SUBJECTS = ["the user", "their daughter", "their doctor", "their manager", "their partner"]
_TOPICS = [
    "prefers worked examples over abstract theory when learning",
    "is allergic to shellfish and avoids seafood",
    "switched jobs last month to a fintech startup",
    "takes metformin every morning for blood sugar",
    "struggles to focus during long study sessions",
    "is vegetarian and cooks most meals at home",
    "is saving aggressively for a house deposit",
    "feels burned out after the recent product launch",
    "plays the cello on Tuesday evenings",
    "has a recurring migraine triggered by poor sleep",
    "is learning Rust for a side project",
    "dislikes early morning meetings",
    "manages anxiety with weekly therapy",
    "uses a standing desk for back pain",
    "prefers async written updates over status calls",
]
_PARAPHRASE = {
    "learning": "how does this person like to be taught",
    "allergic": "what foods must this person avoid",
    "metformin": "what daily prescription does this person take",
    "burned out": "is this person exhausted from work",
    "vegetarian": "what are this person's dietary restrictions",
    "house": "what is this person saving money for",
    "therapy": "how does this person handle mental health",
}


def _cosine_matrix_topk(
    queries: list[list[float]], corpus: list[list[float]], k: int
) -> list[list[int]]:
    import numpy as np

    q = np.asarray(queries, dtype=np.float32)
    c = np.asarray(corpus, dtype=np.float32)
    sims = q @ c.T  # vectors are L2-normalised → dot = cosine
    return [list(np.argsort(-sims[i])[:k]) for i in range(len(queries))]


def test_turbovec_4bit_recall_at_10_clears_the_bar() -> None:
    pytest.importorskip("turbovec")
    rng_seed = 42
    try:
        from persona.stores.embedder import SentenceTransformerEmbedder
    except ImportError:  # pragma: no cover
        pytest.skip("sentence-transformers not installed")

    from persona.graph.index_turbovec import TurbovecGraphIndex

    # Deterministic corpus + paraphrase queries (no Math.random — fixed seed via index).
    corpus = [
        f"{_SUBJECTS[i % len(_SUBJECTS)]} {_TOPICS[(i // len(_SUBJECTS)) % len(_TOPICS)]} (#{i})"
        for i in range(_N_CORPUS)
    ]
    queries: list[str] = []
    for i in range(_N_QUERY):
        src = _TOPICS[i % len(_TOPICS)]
        q = next((p for kw, p in _PARAPHRASE.items() if kw in src), None)
        queries.append(q or f"tell me about {' '.join(src.split()[:4])}")

    emb = SentenceTransformerEmbedder(device="auto")
    cvecs = emb.encode(corpus)
    qvecs = emb.encode(queries)
    assert len(cvecs[0]) == 384

    float32 = {i: cvecs[i] for i in range(_N_CORPUS)}
    baseline = _cosine_matrix_topk(qvecs, cvecs, _K)  # float32 brute force (== pgvector)

    idx = TurbovecGraphIndex(
        float32_fetch=lambda surrogates: {s: float32[s] for s in surrogates},
        dim=384,
        bit_width=4,
        rerank_n=50,
    )

    idx.rebuild([(i, cvecs[i]) for i in range(_N_CORPUS)])  # one bulk add → calibrated

    recalls: list[float] = []
    for i in range(_N_QUERY):
        got = {s for s, _ in idx.search(query_vector=qvecs[i], top_k=_K)}
        truth = set(baseline[i])
        recalls.append(len(got & truth) / _K)
    mean_recall = sum(recalls) / len(recalls)
    assert mean_recall >= _RECALL_BAR, (
        f"4-bit+rerank recall@{_K} = {mean_recall:.3f} < {_RECALL_BAR} "
        f"(rng_seed={rng_seed}, n={_N_CORPUS})"
    )

    # Allowlist parity: a restricted search returns only allowlisted surrogates.
    allow = list(range(50))
    restricted = idx.search(query_vector=qvecs[0], top_k=_K, allowlist=allow)
    assert {s for s, _ in restricted} <= set(allow)
    assert not math.isnan(mean_recall)
