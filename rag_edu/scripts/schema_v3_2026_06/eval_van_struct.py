#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Văn theo_trang + theo_bài eval — does structured-exact (title CONTAINS trang/bài) work for Văn?
Grounded on Văn chunks that HAVE trang_no / lesson_no. Emulates query_structured_exact."""
import re, unicodedata, random
from collections import defaultdict
from neo4j import GraphDatabase
drv=GraphDatabase.driver("bolt://localhost:7688",auth=("neo4j","CHANGEME_NEO4J_PASS"))
random.seed(11)
def fold(s):
    s=(s or "").replace("đ","d").replace("Đ","D"); s=unicodedata.normalize("NFD",s)
    return "".join(c for c in s if unicodedata.category(c)!="Mn").lower()

with drv.session() as s:
    pages=[dict(r) for r in s.run("""MATCH (k:KnowledgeChunk) WHERE k.subject_code='ngu_van' AND k.production_ready=true
        AND toInteger(k.grade)>=6 AND toInteger(k.grade)<=9 AND k.trang_no IS NOT NULL
        RETURN toInteger(k.grade) AS g, k.bo_sach AS bo, k.trang_no AS trang""")]
    bais=[dict(r) for r in s.run("""MATCH (k:KnowledgeChunk) WHERE k.subject_code='ngu_van' AND k.production_ready=true
        AND toInteger(k.grade)>=6 AND toInteger(k.grade)<=9 AND k.lesson_no IS NOT NULL
        RETURN toInteger(k.grade) AS g, k.bo_sach AS bo, k.lesson_no AS ln""")]
print(f"page anchors: {len(pages)} | bai anchors: {len(bais)}")

T_TR=["soạn bài trang {p} ngữ văn {g}","ngữ văn {g} trang {p}","phần trang {p} làm sao ạ","trang {p} sách văn {g}"]
T_BAI=["bài {n} ngữ văn {g}","soạn bài {n} văn {g}","em đang học bài {n} ngữ văn"]

def struct_retrieve(p, sess):
    cy="""MATCH (k:KnowledgeChunk) WHERE k.subject_code='ngu_van' AND coalesce(k.production_ready,false)=true
            AND (k.grade=$g OR toString(k.grade)=toString($g)) AND k.bo_sach=$bo """
    params={"g":p["g"],"bo":p["bo"]}
    if p.get("trang"):
        cy+=" AND toLower(k.title) CONTAINS $tr "; params["tr"]=f"trang {p['trang']}"
    if p.get("ln"):
        cy+=" AND (k.lesson_no=$ln OR toLower(k.title) CONTAINS $bc) "; params["ln"]=p["ln"]; params["bc"]=f"bài {p['ln']}:"
    cy+=" RETURN k.grade AS g, k.trang_no AS trang, k.lesson_no AS ln, k.title AS title LIMIT 1"
    r=sess.run(cy, **params).data()
    return r[0] if r else None

res=defaultdict(lambda:{"n":0,"hit":0,"leak":0})
with drv.session() as sess:
    # theo_trang
    for _ in range(500):
        a=random.choice(pages); q=random.choice(T_TR).format(p=a["trang"],g=a["g"])
        r=struct_retrieve({"g":a["g"],"bo":a["bo"],"trang":a["trang"]}, sess)
        res["theo_trang"]["n"]+=1
        if r:
            if str(r["g"])!=str(a["g"]): res["theo_trang"]["leak"]+=1
            elif str(r.get("trang"))==str(a["trang"]): res["theo_trang"]["hit"]+=1
    # theo_bai
    for _ in range(500):
        a=random.choice(bais); q=random.choice(T_BAI).format(n=a["ln"],g=a["g"])
        r=struct_retrieve({"g":a["g"],"bo":a["bo"],"ln":a["ln"]}, sess)
        res["theo_bai"]["n"]+=1
        if r:
            if str(r["g"])!=str(a["g"]): res["theo_bai"]["leak"]+=1
            elif str(r.get("ln"))==str(a["ln"]): res["theo_bai"]["hit"]+=1
print("\n=== Văn structured ===")
for t,c in res.items():
    print(f"  {t:11}: {100*c['hit']/c['n']:5.1f}% ({c['hit']}/{c['n']}) leak={c['leak']}")
drv.close()
