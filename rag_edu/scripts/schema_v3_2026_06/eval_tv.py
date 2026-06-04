#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TV G1-5 eval: template (scale) + Gemma4 natural-language sample. Emulate structured + concept-exact."""
import re, unicodedata, random, requests
from collections import defaultdict
from neo4j import GraphDatabase
drv=GraphDatabase.driver("bolt://localhost:7688",auth=("neo4j","CHANGEME_NEO4J_PASS"))
GEMMA="http://localhost:8080/v1/chat/completions"; KEY="CHANGEME_GEMMA_KEY"
random.seed(9)
def fold(s):
    s=(s or "").replace("đ","d").replace("Đ","D").replace("–","-"); s=unicodedata.normalize("NFD",s)
    return "".join(c for c in s if unicodedata.category(c)!="Mn").lower()
def gemma(p):
    try:
        b={"model":"gemma-4","messages":[{"role":"system","content":"Mô phỏng học sinh tiểu học VN nói với gia sư AI, giọng nói tự nhiên khẩu ngữ, có 'ơi/ạ/với'."},{"role":"user","content":p}],"max_tokens":70,"temperature":1.0}
        return requests.post(GEMMA,headers={"Authorization":f"Bearer {KEY}"},json=b,timeout=40).json()["choices"][0]["message"]["content"].strip().strip('"').split("\n")[0]
    except: return "[err]"

def retrieve(q,g,bo,sess):
    ql=q.lower(); qf=fold(q)
    mb=re.search(r"\bb[àa]i\s*(\d+)",ql); mt=re.search(r"\btrang\s*(\d+)",ql)
    if mb or mt:
        cy="MATCH (k:KnowledgeChunk) WHERE k.subject_code='tieng_viet' AND coalesce(k.production_ready,false)=true AND (k.grade=$g OR toString(k.grade)=toString($g)) AND k.bo_sach=$bo "
        p={"g":g,"bo":bo}
        if mb: cy+=" AND (k.lesson_no=$bai OR toLower(k.title) CONTAINS $bc) "; p["bai"]=int(mb.group(1)); p["bc"]=f"bài {mb.group(1)}:"
        if mt: cy+=" AND toLower(k.title) CONTAINS $tr "; p["tr"]=f"trang {mt.group(1)}"
        cy+=" RETURN k.grade AS g, k.title AS title, k.lesson_no AS ln, k.trang_no AS trang ORDER BY CASE WHEN k.content_class='tv_lesson' THEN 0 ELSE 1 END LIMIT 1"
        r=sess.run(cy,**p).data()
        if r: return ("struct",r[0])
    cy="""MATCH (k:KnowledgeChunk)-[:COVERS]->(c:Concept) WHERE coalesce(k.production_ready,false)=true AND (k.grade=$g OR toString(k.grade)=toString($g)) AND k.bo_sach=$bo AND k.subject_code='tieng_viet' AND c.name_norm IS NOT NULL AND size(c.name_norm)>=3
      WITH k,c,$qf AS q WITH k,c,q,[w IN split(c.name_norm,' ') WHERE size(w)>=4] AS cw WITH k,c,q,cw,[w IN cw WHERE q CONTAINS w] AS h
      WHERE q CONTAINS c.name_norm OR (size(cw)>=2 AND size(h)>=2)
      RETURN k.grade AS g, c.name AS concept,(CASE WHEN q CONTAINS c.name_norm THEN 1000 ELSE size(h) END) AS ms ORDER BY ms DESC, size(c.name_norm) DESC LIMIT 1"""
    r=sess.run(cy,g=g,bo=bo,qf=qf).data()
    return ("concept",r[0]) if r else ("miss",None)

with drv.session() as s:
    les=[dict(r) for r in s.run("MATCH (k:KnowledgeChunk) WHERE k.subject_code='tieng_viet' AND k.production_ready=true AND k.lesson_no IS NOT NULL AND k.title=~'.*B[àa]i \\\\d+:.*' RETURN toInteger(k.grade) AS g,k.bo_sach AS bo,k.lesson_no AS ln")]
    pg=[dict(r) for r in s.run("MATCH (k:KnowledgeChunk) WHERE k.subject_code='tieng_viet' AND k.production_ready=true AND k.trang_no IS NOT NULL RETURN toInteger(k.grade) AS g,k.bo_sach AS bo,k.trang_no AS trang")]
    con=[dict(r) for r in s.run("MATCH (c:Concept {subject:'tieng_viet'})<-[:COVERS]-(k:KnowledgeChunk {production_ready:true}) RETURN DISTINCT toInteger(k.grade) AS g,k.bo_sach AS bo,c.name AS concept")]
print(f"anchors: lessons={len(les)} pages={len(pg)} concepts={len(con)}")

T_BAI=["bài {n} tiếng việt lớp {g}","cô ơi giảng bài {n} với ạ","em đang học bài {n} tiếng việt"]
T_TR=["trang {p} tiếng việt lớp {g}","cô ơi giải trang {p} với ạ","bài ở trang {p} làm sao ạ"]
T_KT=["bài {c} kể về gì ạ","cô ơi giảng bài {c}","{c} là bài gì ạ","đọc bài {c} cho em"]
res=defaultdict(lambda:{"n":0,"hit":0,"leak":0})
with drv.session() as sess:
    for _ in range(400):
        a=random.choice(les); q=random.choice(T_BAI).format(n=a["ln"],g=a["g"]); t,r=retrieve(q,a["g"],a["bo"],sess)
        res["theo_bai"]["n"]+=1
        if r:
            if str(r["g"])!=str(a["g"]): res["theo_bai"]["leak"]+=1
            elif r.get("ln")==a["ln"]: res["theo_bai"]["hit"]+=1
    for _ in range(400):
        a=random.choice(pg); q=random.choice(T_TR).format(p=a["trang"],g=a["g"]); t,r=retrieve(q,a["g"],a["bo"],sess)
        res["theo_trang"]["n"]+=1
        if r:
            if str(r["g"])!=str(a["g"]): res["theo_trang"]["leak"]+=1
            elif str(r.get("trang"))==str(a["trang"]): res["theo_trang"]["hit"]+=1
    for _ in range(400):
        a=random.choice(con); q=random.choice(T_KT).format(c=a["concept"]); t,r=retrieve(q,a["g"],a["bo"],sess)
        res["kien_thuc"]["n"]+=1
        if r and t=="concept" and fold(a["concept"]) in fold(r.get("concept","") or ""): res["kien_thuc"]["hit"]+=1
        elif r and str(r.get("g",a["g"]))!=str(a["g"]): res["kien_thuc"]["leak"]+=1
print("\n=== TV template eval ===")
for k,v in res.items(): print(f"  {k:11}: {100*v['hit']/v['n']:5.1f}% ({v['hit']}/{v['n']}) leak={v['leak']}")
tn=sum(v['n'] for v in res.values()); th=sum(v['hit'] for v in res.values())
print(f"  OVERALL(template): {100*th/tn:.1f}%")

# natural sample
print("\n=== TV NATURAL (Gemma4) sample ===")
nat=defaultdict(lambda:{"n":0,"hit":0})
with drv.session() as sess:
    random.shuffle(les); random.shuffle(con)
    for a in les[:12]:
        q=gemma(f"Em học Tiếng Việt lớp {a['g']}. Nhờ cô giảng Bài {a['ln']} — nói 1 câu tự nhiên có nhắc số bài.")
        if q=="[err]": continue
        t,r=retrieve(q,a["g"],a["bo"],sess); hit=r and r.get("ln")==a["ln"]
        nat["bai"]["n"]+=1; nat["bai"]["hit"]+=1 if hit else 0
    for a in con[:12]:
        q=gemma(f"Em học Tiếng Việt lớp {a['g']}. Hỏi cô về bài '{a['concept']}' — 1 câu tự nhiên, KHÔNG nói số bài.")
        if q=="[err]": continue
        t,r=retrieve(q,a["g"],a["bo"],sess); hit=r and fold(a["concept"]) in fold(r.get("concept","") or r.get("title","") or "")
        nat["concept"]["n"]+=1; nat["concept"]["hit"]+=1 if hit else 0
        if nat["concept"]["n"]<=6: print(f"  [{('OK' if hit else 'XX')}] {q[:70]}")
for k,v in nat.items():
    if v["n"]: print(f"  natural/{k}: {100*v['hit']/v['n']:.1f}% ({v['hit']}/{v['n']})")
drv.close()
