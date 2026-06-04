#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Latency benchmark — đo thời gian thực tế của retrieval Cypher (structured + concept).
Path chính KHÔNG gọi model nên phải rất nhanh. Đo p50/p95 over nhiều query."""
import time, re, unicodedata, random
from neo4j import GraphDatabase
drv=GraphDatabase.driver("bolt://localhost:7688",auth=("neo4j","CHANGEME_NEO4J_PASS"))
random.seed(5)
def fold(s):
    s=(s or "").replace("đ","d").replace("Đ","D"); s=unicodedata.normalize("NFD",s)
    return "".join(c for c in s if unicodedata.category(c)!="Mn").lower()

def struct_q(sess,g,bo,bai=None,trang=None):
    cy="MATCH (k:KnowledgeChunk) WHERE k.subject_code='toan' AND coalesce(k.production_ready,false)=true AND (k.grade=$g OR toString(k.grade)=toString($g)) AND k.bo_sach=$bo "
    p={"g":g,"bo":bo}
    if bai: cy+=" AND (k.lesson_no=$bai OR toLower(k.title) CONTAINS $bc) "; p["bai"]=bai; p["bc"]=f"bài {bai}:"
    if trang: cy+=" AND toLower(k.title) CONTAINS $tr "; p["tr"]=f"trang {trang}"
    cy+=" RETURN k.title LIMIT 1"
    return sess.run(cy,**p).consume()

def concept_q(sess,g,bo,qf):
    cy="""MATCH (k:KnowledgeChunk)-[:COVERS]->(c:Concept) WHERE coalesce(k.production_ready,false)=true AND (k.grade=$g OR toString(k.grade)=toString($g)) AND k.bo_sach=$bo AND k.subject_code='toan' AND c.name_norm IS NOT NULL AND size(c.name_norm)>=3
      WITH k,c,$qf AS q WITH k,c,q,[w IN split(c.name_norm,' ') WHERE size(w)>=4] AS cw WITH k,c,q,cw,[w IN cw WHERE q CONTAINS w] AS h
      WHERE q CONTAINS c.name_norm OR (size(cw)>=2 AND size(h)>=2)
      RETURN c.name,(CASE WHEN q CONTAINS c.name_norm THEN 1000 ELSE size(h) END) AS ms ORDER BY ms DESC LIMIT 1"""
    return sess.run(cy,g=g,bo=bo,qf=qf).consume()

def pct(xs,p): xs=sorted(xs); return xs[int(len(xs)*p)] if xs else 0

with drv.session() as sess:
    # warmup
    for _ in range(5): struct_q(sess,6,"KNTT",bai=1)
    st=[]; ct=[]
    for i in range(300):
        g=random.choice([1,2,3,4,5,6,7,8,9]); bo=random.choice(["KNTT","CTST","CD"])
        t=time.time(); struct_q(sess,g,bo,bai=random.randint(1,40)); st.append((time.time()-t)*1000)
    for i in range(300):
        g=random.choice([6,7,8,9]); bo=random.choice(["KNTT","CTST","CD"])
        t=time.time(); concept_q(sess,g,bo,fold("phương trình bậc hai là gì")); ct.append((time.time()-t)*1000)
print("=== Cypher retrieval latency (300 queries each, ms) ===")
print(f"structured-exact (bài/trang):  p50={pct(st,.5):.1f}  p95={pct(st,.95):.1f}  max={max(st):.1f}")
print(f"concept-exact (word-overlap):  p50={pct(ct,.5):.1f}  p95={pct(ct,.95):.1f}  max={max(ct):.1f}")
print("\nNote: đây là TOÀN BỘ chi phí path chính (Tier A) — KHÔNG gọi LLM/embed model.")
drv.close()
