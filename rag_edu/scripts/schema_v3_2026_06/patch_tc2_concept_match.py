#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T-C2: improve query_concept_exact — partial concept match via word-overlap
(not just full-name CONTAINS). Catches 'định lí Thalès' for 'Định lí Thalès trong tam giác'."""
import shutil, py_compile, sys
F = "/home/namnx/Ptalk_project/CloudPTalk/rag_server_canary.py"
shutil.copy(F, F + ".bak_pre_TC2_2026_06_03")
src = open(F, encoding="utf-8").read()

old = '''    cypher = """
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
    """'''

new = '''    cypher = """
        MATCH (k:KnowledgeChunk)-[:COVERS]->(c:Concept)
        WHERE coalesce(k.production_ready,false) = true
          AND (k.grade = $grade OR toString(k.grade) = toString($grade))
          AND k.bo_sach = $bo_sach
          AND ($subject IS NULL OR k.subject_code = $subject)
          AND c.name_norm IS NOT NULL AND size(c.name_norm) >= 3
        WITH k, c, $q_folded AS q
        WITH k, c, q, [w IN split(c.name_norm,' ') WHERE size(w) >= 4] AS cw
        WITH k, c, q, cw, [w IN cw WHERE q CONTAINS w] AS hits
        WHERE q CONTAINS c.name_norm
           OR (size(cw) >= 2 AND size(hits) >= 2)
        RETURN k.title AS title, k.grade AS grade, k.bo_sach AS bo_sach,
               k.text AS text, k.subject_code AS subj, c.name AS concept,
               size(c.name_norm) AS clen,
               (CASE WHEN q CONTAINS c.name_norm THEN 1000 ELSE size(hits) END) AS mscore
        ORDER BY
            mscore DESC,
            CASE WHEN k.content_class = 'vietjack_lesson' THEN 0 ELSE 1 END,
            clen DESC, size(k.text) DESC
        LIMIT 3
    """'''

assert old in src, "T-C2 anchor not found"
src = src.replace(old, new, 1)
open(F, "w", encoding="utf-8").write(src)
try:
    py_compile.compile(F, doraise=True)
    print("T-C2 applied + py_compile OK")
except py_compile.PyCompileError as e:
    shutil.copy(F + ".bak_pre_TC2_2026_06_03", F)
    print(f"COMPILE FAIL, rolled back: {e}")
    sys.exit(1)
