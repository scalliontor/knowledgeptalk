#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T-C: patch rag_server_canary.py — (1) fix grade propagation (cross-grade leak),
(2) add concept-exact Tier-A path for topic-only queries. Backup + verify."""
import shutil, py_compile, sys

F = "/home/namnx/Ptalk_project/CloudPTalk/rag_server_canary.py"
BAK = F + ".bak_pre_TC_2026_06_03"
shutil.copy(F, BAK)
print(f"backup → {BAK}")

src = open(F, encoding="utf-8").read()

# ── PATCH 1: grade propagation fix ──────────────────────────
old1 = '''    intent = route_query(req.query)
    intent.update({k: v for k, v in parsed.items() if v is not None and k in ("lop", "bo_sach")})'''
new1 = '''    intent = route_query(req.query)
    intent.update({k: v for k, v in parsed.items() if v is not None and k in ("lop", "bo_sach")})
    # T-C fix: retrieval fns read intent["grade"]; parsed uses "lop" → propagate (cross-grade leak fix)
    if parsed.get("lop"):
        intent["grade"] = parsed["lop"]'''
assert old1 in src, "PATCH1 anchor not found"
src = src.replace(old1, new1, 1)
print("PATCH1 applied (grade propagation)")

# ── PATCH 2a: new query_concept_exact function (before query_structured_exact) ──
anchor2 = 'def query_structured_exact(parsed: Dict[str, Any]) -> str:'
assert anchor2 in src, "PATCH2 anchor not found"
fn = '''def query_concept_exact(parsed: Dict[str, Any], query: str) -> str:
    """Tier A-concept: topic-only query (no bai/trang) -> exact lookup by Concept name within grade+book."""
    grade = parsed.get("lop")
    bo_sach = parsed.get("bo_sach")
    subject = parsed.get("subject")
    if not (grade and bo_sach):
        return ""
    q_folded = _fold(query)
    cypher = """
        MATCH (k:KnowledgeChunk)-[:COVERS]->(c:Concept)
        WHERE coalesce(k.production_ready,false) = true
          AND (k.grade = $grade OR toString(k.grade) = toString($grade))
          AND k.bo_sach = $bo_sach
          AND ($subject IS NULL OR k.subject_code = $subject)
          AND c.name_norm IS NOT NULL AND size(c.name_norm) >= 4
          AND $q_folded CONTAINS c.name_norm
        RETURN k.title AS title, k.grade AS grade, k.bo_sach AS bo_sach,
               k.text AS text, k.subject_code AS subj, c.name AS concept,
               size(c.name_norm) AS clen
        ORDER BY
            CASE WHEN k.content_class = 'vietjack_lesson' THEN 0 ELSE 1 END,
            clen DESC, size(k.text) DESC
        LIMIT 3
    """
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
        with driver.session() as s:
            results = s.run(cypher, grade=grade, bo_sach=bo_sach,
                            subject=subject, q_folded=q_folded).data()
        driver.close()
    except Exception as e:
        print(f"[Concept Exact Error] {e}")
        return ""
    if not results:
        return ""
    contexts = []
    for r in results:
        meta = f"L\\u1edbp {r['grade']} | {r['bo_sach']} | {r['subj']}"
        contexts.append(f"\\U0001f4d0 {r['title']} ({meta}) [concept: {r['concept']}]\\n{(r['text'] or '')[:4000]}")
    return "\\n\\n".join(contexts)


'''
src = src.replace(anchor2, fn + anchor2, 1)
print("PATCH2a applied (query_concept_exact fn)")

# ── PATCH 2b: wire concept-exact into retrieve() after Tier A structured ──
old2b = '''            ctx = unicodedata.normalize('NFC', f"[DỮ LIỆU EXACT - TIER A]\\nNguồn chính:\\n{tier_a_ctx}")
            return RetrieveResponse(context=ctx, intent=intent_a, sources=["tier_a_structured"])'''
new2b = old2b + '''

    # ── TIER A-concept: topic-only query (no bai/trang) -> concept exact lookup ──
    if not (parsed.get("bai_no") or parsed.get("trang")) and parsed.get("lop") and parsed.get("bo_sach"):
        concept_ctx = query_concept_exact(parsed, req.query)
        if concept_ctx:
            print(f"[RAG] \\u2705 Tier A-concept hit ({len(concept_ctx)} chars)")
            intent_c = {
                "need_rag": True, "subject": parsed.get("subject"),
                "grade": parsed.get("lop"), "bo_sach": parsed.get("bo_sach"),
                "query_type": "explain", "learning_mode": "tutor", "tier": "A_concept",
            }
            ctx = unicodedata.normalize('NFC', f"[D\\u1eEC LI\\u1eC6U CONCEPT - TIER A]\\nNgu\\u1ed3n ch\\xednh:\\n{concept_ctx}")
            return RetrieveResponse(context=ctx, intent=intent_c, sources=["tier_a_concept"])'''
assert old2b in src, "PATCH2b anchor not found"
src = src.replace(old2b, new2b, 1)
print("PATCH2b applied (wire concept-exact)")

open(F, "w", encoding="utf-8").write(src)

# verify compile
try:
    py_compile.compile(F, doraise=True)
    print("py_compile OK")
except py_compile.PyCompileError as e:
    print(f"COMPILE FAIL: {e}")
    shutil.copy(BAK, F)
    print("ROLLED BACK")
    sys.exit(1)
