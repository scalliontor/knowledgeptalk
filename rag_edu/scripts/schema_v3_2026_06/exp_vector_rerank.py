#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""EXPERIMENT: does BGE vector-rerank fix concept-only paraphrase queries that concept-exact misses?
A/B: concept-exact (Cypher) vs BGE vector search (grade+book filtered). Standalone BGE load (no uvicorn)."""
import re, unicodedata, random, requests, time
from collections import defaultdict
from neo4j import GraphDatabase
print("loading BGE-m3...", flush=True)
t0=time.time()
from sentence_transformers import SentenceTransformer
bge=SentenceTransformer("BAAI/bge-m3")
print(f"BGE loaded in {time.time()-t0:.1f}s", flush=True)
drv=GraphDatabase.driver("bolt://localhost:7688",auth=("neo4j","CHANGEME_NEO4J_PASS"))
GEMMA="http://localhost:8080/v1/chat/completions"; KEY="CHANGEME_GEMMA_KEY"; random.seed(13)
def fold(s):
    s=(s or "").replace("đ","d").replace("Đ","D").replace("–","-"); s=unicodedata.normalize("NFD",s)
    return "".join(c for c in s if unicodedata.category(c)!="Mn").lower()
def gemma(p):
    try:
        b={"model":"gemma-4","messages":[{"role":"system","content":"Mô phỏng học sinh VN hỏi gia sư bằng giọng nói. Quan trọng: MÔ TẢ nội dung/ý cần hỏi mà KHÔNG nói tên bài/khái niệm trực tiếp."},{"role":"user","content":p}],"max_tokens":70,"temperature":1.0}
        return requests.post(GEMMA,headers={"Authorization":f"Bearer {KEY}"},json=b,timeout=40).json()["choices"][0]["message"]["content"].strip().strip('"').split("\n")[0]
    except: return "[err]"

def concept_exact(qf,g,bo,subj,sess):
    cy="""MATCH (k:KnowledgeChunk)-[:COVERS]->(c:Concept) WHERE coalesce(k.production_ready,false)=true AND (k.grade=$g OR toString(k.grade)=toString($g)) AND k.bo_sach=$bo AND k.subject_code=$subj AND c.name_norm IS NOT NULL AND size(c.name_norm)>=3
      WITH k,c,$qf AS q WITH k,c,q,[w IN split(c.name_norm,' ') WHERE size(w)>=4] AS cw WITH k,c,q,cw,[w IN cw WHERE q CONTAINS w] AS h
      WHERE q CONTAINS c.name_norm OR (size(cw)>=2 AND size(h)>=2)
      RETURN c.name AS concept ORDER BY (CASE WHEN q CONTAINS c.name_norm THEN 1000 ELSE size(h) END) DESC, size(c.name_norm) DESC LIMIT 1"""
    r=sess.run(cy,qf=qf,g=g,bo=bo,subj=subj).data()
    return r[0]["concept"] if r else None

def vector(qvec,g,bo,subj,sess):
    cy="""CALL db.index.vector.queryNodes('knowledge_chunk_embedding', 60, $qv) YIELD node AS k, score
      WHERE k.subject_code=$subj AND (k.grade=$g OR toString(k.grade)=toString($g)) AND k.bo_sach=$bo AND coalesce(k.production_ready,false)=true
      RETURN coalesce(k.concept_name, k.work_name, k.title) AS concept, k.title AS title, score ORDER BY score DESC LIMIT 1"""
    r=sess.run(cy,qv=qvec,g=g,bo=bo,subj=subj).data()
    return r[0] if r else None

# anchors: concept + grade + book (Toán + TV — the weak concept subjects)
with drv.session() as s:
    anc=[dict(r) for r in s.run("""MATCH (c:Concept {subject:'toan',level:'fine'})<-[:COVERS]-(k:KnowledgeChunk {production_ready:true})
        WHERE size(c.name)>8 RETURN DISTINCT toInteger(k.grade) AS g,k.bo_sach AS bo,'toan' AS subj,c.name AS concept ORDER BY rand() LIMIT 18""")]
    anc+=[dict(r) for r in s.run("""MATCH (c:Concept {subject:'tieng_viet',level:'fine'})<-[:COVERS]-(k:KnowledgeChunk {production_ready:true})
        WHERE size(c.name)>8 RETURN DISTINCT toInteger(k.grade) AS g,k.bo_sach AS bo,'tieng_viet' AS subj,c.name AS concept ORDER BY rand() LIMIT 12""")]

print(f"\n=== A/B on {len(anc)} paraphrase queries (concept-exact vs BGE vector) ===\n", flush=True)
ce_hit=ve_hit=n=0
with drv.session() as sess:
    for a in anc:
        q=gemma(f"Em học {('Toán' if a['subj']=='toan' else 'Tiếng Việt')} lớp {a['g']}. Hỏi gia sư về bài/khái niệm '{a['concept']}' nhưng MÔ TẢ ý chứ đừng nói tên. 1 câu tự nhiên.")
        if q=="[err]": continue
        n+=1; qf=fold(q); qv=bge.encode([q],normalize_embeddings=True)[0].tolist()
        ce=concept_exact(qf,a["g"],a["bo"],a["subj"],sess)
        ve=vector(qv,a["g"],a["bo"],a["subj"],sess)
        ce_ok = ce and fold(a["concept"]) in fold(ce)
        ve_ok = ve and fold(a["concept"]) in fold(ve.get("concept","") or "")
        ce_hit+=1 if ce_ok else 0; ve_hit+=1 if ve_ok else 0
        print(f"[{a['subj'][:4]} G{a['g']}] want={a['concept'][:30]!r}")
        print(f"   Q: {q[:72]}")
        print(f"   concept-exact: {'OK' if ce_ok else 'XX'} ({str(ce)[:28]})   |   VECTOR: {'OK' if ve_ok else 'XX'} ({str(ve.get('concept') if ve else None)[:28]})")
print(f"\n=== RESULT ({n} paraphrase queries) ===")
print(f"  concept-exact: {100*ce_hit/n:.1f}% ({ce_hit}/{n})")
print(f"  BGE vector:    {100*ve_hit/n:.1f}% ({ve_hit}/{n})")
drv.close()
