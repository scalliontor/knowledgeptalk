#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Backfill G1-5 Toán lesson_no/trang_no/tap_no from title.
Title: 'Toán lớp G [bộ] Bài N: <concept> (trang P[, P2..] [Tập T]) - [bộ]'.
Primary numbers bài continuously (no cross-chapter collision)."""
import re
from neo4j import GraphDatabase
drv = GraphDatabase.driver("bolt://localhost:7688", auth=("neo4j","CHANGEME_NEO4J_PASS"))
ACTOR="G15_BACKFILL_2026_06_03"

with drv.session() as s:
    rows=list(s.run("""
        MATCH (k:KnowledgeChunk) WHERE k.subject_code='toan' AND k.production_ready=true
          AND toInteger(k.grade)>=1 AND toInteger(k.grade)<=5
        RETURN k.uid AS uid, k.title AS title, k.lesson_no AS ln
    """))
print(f"G1-5 toan prod chunks: {len(rows)}")

upd=0; lesson_pages=0; widgets=0
with drv.session() as s:
    for r in rows:
        t=r["title"] or ""
        m_bai=re.search(r'B[àa]i\s+(\d+)\s*:', t)
        if not m_bai:
            widgets+=1; continue   # exercise widget / no lesson — leave NULL
        ln=int(m_bai.group(1))
        m_tr=re.search(r'trang\s+(\d+)', t)
        trang=int(m_tr.group(1)) if m_tr else None
        m_tap=re.search(r'T[ậa]p\s+(\d+)', t)
        tap=int(m_tap.group(1)) if m_tap else None
        s.run("""MATCH (k:KnowledgeChunk {uid:$uid})
                 SET k.lesson_no=$ln, k.content_class='vietjack_lesson',
                     k.trang_no=coalesce($trang, k.trang_no),
                     k.tap_no=coalesce($tap, k.tap_no), k.g15_actor=$a""",
              uid=r["uid"], ln=ln, trang=trang, tap=tap, a=ACTOR)
        upd+=1; lesson_pages+=1

print(f"backfilled lesson_no: {upd} | widgets(left NULL): {widgets}")

with drv.session() as s:
    v=s.run("""MATCH (k:KnowledgeChunk) WHERE k.subject_code='toan' AND k.production_ready=true
               AND toInteger(k.grade)>=1 AND toInteger(k.grade)<=5
               RETURN count(*) AS tot,
                 sum(CASE WHEN k.lesson_no IS NOT NULL THEN 1 ELSE 0 END) AS with_ln,
                 sum(CASE WHEN k.trang_no IS NOT NULL THEN 1 ELSE 0 END) AS with_tr""").single()
    print(f"VERIFY G1-5: total={v['tot']} with_lesson_no={v['with_ln']} with_trang_no={v['with_tr']}")
    # collision check (primary should be clean)
    coll=s.run("""MATCH (k:KnowledgeChunk) WHERE k.subject_code='toan' AND k.production_ready=true
                  AND toInteger(k.grade)>=1 AND toInteger(k.grade)<=5 AND k.lesson_no IS NOT NULL
                  WITH toInteger(k.grade) AS g, k.bo_sach AS bo, k.lesson_no AS ln, count(DISTINCT k.title) AS dt
                  WHERE dt>1 RETURN count(*) AS colliding_cells""").single()
    print(f"colliding cells (>1 title per lesson_no): {coll['colliding_cells']}")
drv.close()
