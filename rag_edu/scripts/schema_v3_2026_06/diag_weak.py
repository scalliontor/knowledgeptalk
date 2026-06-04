#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Diagnose Toán concept misses + Văn variant misses — log what was asked vs returned."""
import re, unicodedata, random
from neo4j import GraphDatabase
drv=GraphDatabase.driver("bolt://localhost:7688",auth=("neo4j","CHANGEME_NEO4J_PASS"))
random.seed(3)
def fold(s):
    s=(s or "").replace("đ","d").replace("Đ","D"); s=unicodedata.normalize("NFD",s)
    return "".join(c for c in s if unicodedata.category(c)!="Mn").lower()

# ---- Toán concept misses ----
def concept_retrieve(qf, g, bo, sess):
    cy="""MATCH (k:KnowledgeChunk)-[:COVERS]->(c:Concept)
          WHERE coalesce(k.production_ready,false)=true AND (k.grade=$g OR toString(k.grade)=toString($g))
            AND k.bo_sach=$bo AND k.subject_code='toan' AND c.name_norm IS NOT NULL AND size(c.name_norm)>=3
          WITH k,c,$qf AS q
          WITH k,c,q,[w IN split(c.name_norm,' ') WHERE size(w)>=4] AS cw
          WITH k,c,q,cw,[w IN cw WHERE q CONTAINS w] AS hits
          WHERE q CONTAINS c.name_norm OR (size(cw)>=2 AND size(hits)>=2)
          RETURN c.name AS concept, (CASE WHEN q CONTAINS c.name_norm THEN 1000 ELSE size(hits) END) AS ms
          ORDER BY ms DESC, size(c.name_norm) DESC LIMIT 1"""
    r=sess.run(cy,g=g,bo=bo,qf=qf).data()
    return r[0]["concept"] if r else None

print("=== TOÁN concept misses (asked vs got) ===")
with drv.session() as s:
    concepts=[dict(r) for r in s.run("""MATCH (c:Concept {subject:'toan',level:'fine'})<-[:COVERS]-(k:KnowledgeChunk {production_ready:true})
        RETURN DISTINCT toInteger(k.grade) AS g, k.bo_sach AS bo, c.name AS concept""")]
    misses=0; shown=0
    random.shuffle(concepts)
    for a in concepts:
        q=f"{a['concept']} là gì"; got=concept_retrieve(fold(q), a["g"], a["bo"], s)
        hit = got and (fold(a["concept"]) in fold(got) or fold(got) in fold(a["concept"]))
        if not hit:
            misses+=1
            if shown<18:
                print(f"  ASK[G{a['g']} {a['bo']}]: {a['concept'][:45]!r}  → GOT: {got!r}")
                shown+=1
    print(f"  total misses sampled: {misses}/{len(concepts)}")

# ---- Văn variant misses ----
print("\n=== VĂN variant misses ===")
with drv.session() as s:
    rows=[dict(r) for r in s.run("""MATCH (k:KnowledgeChunk) WHERE k.subject_code='ngu_van' AND k.production_ready=true
        AND k.work_name IS NOT NULL AND k.variant<>'standard' AND toInteger(k.grade)>=6 AND toInteger(k.grade)<=9
        RETURN DISTINCT toInteger(k.grade) AS g, k.bo_sach AS bo, k.work_name AS work, k.variant AS variant""")]
    # for each (work,variant), check if requesting that variant returns it
    VAR={"chi_tiet":"chi tiết","sieu_ngan":"siêu ngắn","ngan_nhat":"ngắn nhất"}
    miss=0; shown=0
    for a in rows[:80]:
        qf=fold(f"soạn {a['work']} {VAR.get(a['variant'],'')}")
        r=s.run("""MATCH (k:KnowledgeChunk) WHERE k.subject_code='ngu_van' AND k.production_ready=true
            AND (k.grade=$g OR toString(k.grade)=toString($g)) AND k.bo_sach=$bo AND k.work_name_norm IS NOT NULL
            AND q_contains_work AND k.variant=$var
            RETURN k.variant AS v LIMIT 1""".replace("q_contains_work","$qf CONTAINS k.work_name_norm"),
            g=a["g"],bo=a["bo"],qf=qf,var=a["variant"]).data()
        if not r:
            miss+=1
            if shown<10:
                # what variants DOES this work have?
                vs=s.run("""MATCH (k:KnowledgeChunk {subject_code:'ngu_van',production_ready:true})
                    WHERE k.work_name=$w AND (k.grade=$g OR toString(k.grade)=toString($g)) AND k.bo_sach=$bo
                    RETURN collect(DISTINCT k.variant) AS vs""",w=a["work"],g=a["g"],bo=a["bo"]).single()["vs"]
                print(f"  ASK {a['variant']} of {a['work'][:35]!r} [G{a['g']} {a['bo']}] → work has variants: {vs}")
                shown+=1
    print(f"  variant misses: {miss}/{min(80,len(rows))}")
drv.close()
