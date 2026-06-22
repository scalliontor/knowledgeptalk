"""Embedding-based intent classifier (recite / practice / explain).

EXTRACTED from /tmp/refsrc_canary.py. `_INTENT_ANCHORS` is byte-for-byte.

The original `_classify_intent(query)` read two module globals: `bge_m3_model`
(the BGE model) and `_INTENT_EMB` (precomputed anchor embeddings). To keep this
module import-clean (NO model load, NO side effects), the model and precomputed
embeddings are now INJECTED:

    classify_intent(query, model, intent_emb)

`build_intent_emb(model)` is the precompute step lifted verbatim from the
original module-level `_INTENT_EMB = {...}` dict-comprehension. The 0.035 margin
threshold and the comparison logic are unchanged.
"""
from __future__ import annotations


# ── Intent classifier bằng embedding (robust với paraphrase, không cần Gemma) ──
_INTENT_ANCHORS = {
    "recite": ["đọc thuộc bài thơ này", "đọc cả bài cho mình nghe", "đọc full toàn bộ bài",
               "đọc bài thơ này lên", "ngâm bài thơ", "đọc diễn cảm bài này", "đọc to nguyên bài cho nghe"],
    "practice": ["làm bài tập bài này", "luyện tập trả lời câu hỏi", "giải các câu hỏi trong bài",
                 "cho mình mấy câu để ôn tập", "tự kiểm tra kiến thức", "thực hành làm bài"],
    "explain": ["giảng nội dung bài này", "phân tích ý nghĩa tác phẩm", "tóm tắt nội dung chính",
                "tác giả là ai", "bố cục bài thơ", "giá trị nghệ thuật của bài"],
}


def build_intent_emb(model):
    """Precompute anchor embeddings for each intent.

    Lifted verbatim from the original module-level::

        _INTENT_EMB = {k: [bge_m3_model.encode([p], normalize_embeddings=True)[0].tolist() for p in v]
                       for k, v in _INTENT_ANCHORS.items()}

    Returns {} on failure (mirrors the original try/except guard that set
    `_INTENT_EMB = {}`).
    """
    try:
        return {k: [model.encode([p], normalize_embeddings=True)[0].tolist() for p in v]
                for k, v in _INTENT_ANCHORS.items()}
    except Exception as _e:
        return {}


def classify_intent(query, model, intent_emb):
    """Trả 'recite'/'practice'/'explain' theo độ gần ngữ nghĩa; None nếu lỗi.

    NOTE (refactor): `model` (BGE) and `intent_emb` (precomputed anchor
    embeddings from `build_intent_emb`) are INJECTED — they were module globals
    `bge_m3_model` / `_INTENT_EMB` in the source. Body otherwise verbatim.
    """
    if not intent_emb or not query:
        return None
    try:
        qv = model.encode([query], normalize_embeddings=True)[0].tolist()
        sims = {k: max(sum(a*b for a, b in zip(qv, e)) for e in embs) for k, embs in intent_emb.items()}
        top = max(sims, key=sims.get)
        # cần margin rõ so với explain mới chuyển khỏi explain
        if top in ("recite", "practice") and (sims[top] - sims["explain"]) < 0.035:
            return "explain"
        return top
    except Exception:
        return None
