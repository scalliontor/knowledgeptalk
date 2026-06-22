"""Unit tests for the PURE content-vector selection + gate in lesson_card.

`retrieval.lesson_card._pick_content_vec(cands, qv)` is the byte-for-byte
extraction of the top1/top2 selection loop from rag_server_canary.py. The
acceptance gate applied by the caller is, verbatim:

    best is not None AND bs >= 0.50 AND ((bs - bs2) >= 0.04 OR bs >= 0.60)

These tests run FULLY LOCAL — no Neo4j, no Qdrant, no BGE model. Embeddings are
small synthetic vectors so the dot-product similarities are exactly predictable.
We verify (a) the selection picks the highest-similarity candidate and reports the
runner-up, and (b) the margin floor / abs floor gate accepts/rejects at the
documented thresholds.
"""
import sys
import os

# Path wiring is also done by tests/conftest.py; keep this self-contained too so
# the file can be run directly (python tests/test_retrieval_scoring.py).
_HERE = os.path.dirname(os.path.abspath(__file__))
_PKGS = os.path.abspath(os.path.join(_HERE, "..", "packages"))
if _PKGS not in sys.path:
    sys.path.insert(0, _PKGS)

from retrieval.lesson_card import _pick_content_vec  # noqa: E402


# ── the caller's gate, replicated verbatim from the source ──────────
def _gate(best, bs, bs2):
    """Mirror of the in-source acceptance condition (byte-for-byte logic)."""
    return best is not None and bs >= 0.50 and ((bs - bs2) >= 0.04 or bs >= 0.60)


def _cand(work, emb):
    return {"work": work, "emb": emb}


# ── selection (argmax) ──────────────────────────────────────────────
def test_pick_returns_highest_similarity_as_best():
    qv = [1.0, 0.0, 0.0]
    cands = [
        _cand("A", [0.50, 0.0, 0.0]),  # sim 0.50
        _cand("B", [0.90, 0.0, 0.0]),  # sim 0.90  <- best
        _cand("C", [0.70, 0.0, 0.0]),  # sim 0.70  <- runner-up
    ]
    best, bs, bs2 = _pick_content_vec(cands, qv)
    assert best["work"] == "B"
    assert abs(bs - 0.90) < 1e-9
    assert abs(bs2 - 0.70) < 1e-9


def test_pick_skips_candidates_with_empty_embedding():
    # mirrors `if not e: continue` — None / [] embeddings are ignored
    qv = [1.0, 0.0]
    cands = [
        _cand("noemb1", None),
        _cand("noemb2", []),
        _cand("real", [0.80, 0.0]),  # sim 0.80
    ]
    best, bs, bs2 = _pick_content_vec(cands, qv)
    assert best["work"] == "real"
    assert abs(bs - 0.80) < 1e-9
    assert bs2 == -1.0  # only one real candidate -> runner-up stays at the floor


def test_pick_empty_list_returns_floor_sentinels():
    best, bs, bs2 = _pick_content_vec([], [1.0, 0.0])
    assert best is None
    assert bs == -1.0
    assert bs2 == -1.0


# ── gate: margin floor (>=0.04) path ────────────────────────────────
def test_gate_accepts_on_clear_margin_above_floor():
    qv = [1.0, 0.0]
    cands = [
        _cand("top", [0.62, 0.0]),  # sim 0.62
        _cand("next", [0.55, 0.0]),  # sim 0.55 ; margin 0.07 >= 0.04, bs>=0.50
    ]
    best, bs, bs2 = _pick_content_vec(cands, qv)
    assert _gate(best, bs, bs2) is True


def test_gate_rejects_thin_margin_when_below_abs_floor():
    # bs >= 0.50 but margin < 0.04 AND bs < 0.60 -> reject (ambiguous match)
    qv = [1.0, 0.0]
    cands = [
        _cand("top", [0.55, 0.0]),   # sim 0.55
        _cand("next", [0.53, 0.0]),  # sim 0.53 ; margin 0.02 < 0.04, bs 0.55 < 0.60
    ]
    best, bs, bs2 = _pick_content_vec(cands, qv)
    assert (bs - bs2) < 0.04 and bs < 0.60
    assert _gate(best, bs, bs2) is False


# ── gate: absolute floor (bs>=0.60) path overrides thin margin ──────
def test_gate_accepts_thin_margin_when_above_abs_floor():
    # margin < 0.04 but bs >= 0.60 -> accept via the abs-floor OR branch
    qv = [1.0, 0.0]
    cands = [
        _cand("top", [0.61, 0.0]),   # sim 0.61 >= 0.60
        _cand("next", [0.59, 0.0]),  # sim 0.59 ; margin 0.02 < 0.04
    ]
    best, bs, bs2 = _pick_content_vec(cands, qv)
    assert (bs - bs2) < 0.04 and bs >= 0.60
    assert _gate(best, bs, bs2) is True


# ── gate: absolute floor (bs>=0.50) is a hard reject below it ───────
def test_gate_rejects_below_min_floor_even_with_huge_margin():
    # big margin but bs < 0.50 -> reject (not similar enough in absolute terms)
    qv = [1.0, 0.0]
    cands = [
        _cand("top", [0.49, 0.0]),   # sim 0.49 < 0.50
        _cand("next", [0.10, 0.0]),  # margin 0.39 huge, but floor not met
    ]
    best, bs, bs2 = _pick_content_vec(cands, qv)
    assert (bs - bs2) >= 0.04 and bs < 0.50
    assert _gate(best, bs, bs2) is False


def test_gate_accepts_at_min_abs_floor_via_margin_branch():
    # bs sits at/just above the 0.50 absolute floor and is accepted ONLY because
    # the margin branch (>=0.04) holds — bs is below the 0.60 abs-floor branch.
    # (Note: an "exactly 0.04" margin is NOT testable as a clean accept because
    #  0.50-0.46 == 0.03999...8 in IEEE float, i.e. < 0.04 — the source gate would
    #  reject it; we therefore use an unambiguous margin of ~0.08.)
    qv = [1.0, 0.0]
    cands = [
        _cand("top", [0.58, 0.0]),   # sim 0.58 (>=0.50 floor, <0.60)
        _cand("next", [0.50, 0.0]),  # margin ~0.08 >= 0.04
    ]
    best, bs, bs2 = _pick_content_vec(cands, qv)
    assert bs >= 0.50 and bs < 0.60
    assert (bs - bs2) >= 0.04
    assert _gate(best, bs, bs2) is True


def test_gate_just_below_margin_floor_rejects_float_boundary():
    # Documents the IEEE-float reality of the source gate: a nominal 0.04 margin
    # built from 0.50/0.46 is actually 0.03999...8 < 0.04 AND bs 0.50 < 0.60, so
    # the real gate REJECTS. This pins the exact behavior of the extracted code.
    qv = [1.0, 0.0]
    cands = [
        _cand("top", [0.50, 0.0]),
        _cand("next", [0.46, 0.0]),
    ]
    best, bs, bs2 = _pick_content_vec(cands, qv)
    assert (bs - bs2) < 0.04 and bs < 0.60
    assert _gate(best, bs, bs2) is False


if __name__ == "__main__":
    # allow `python tests/test_retrieval_scoring.py` without pytest
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print("PASS", fn.__name__)
        except Exception:
            failed += 1
            print("FAIL", fn.__name__)
            traceback.print_exc()
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
