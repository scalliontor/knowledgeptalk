#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import unicodedata
from neo4j import GraphDatabase
drv=GraphDatabase.driver("bolt://localhost:7688",auth=("neo4j","CHANGEME_NEO4J_PASS"))
def fold(s):
    s=(s or "").replace("đ","d").replace("Đ","D")
    s=unicodedata.normalize("NFD",s)
    return "".join(c for c in s if unicodedata.category(c)!="Mn").lower()
with drv.session() as s:
    rows=list(s.run("MATCH (k:KnowledgeChunk) WHERE k.work_name IS NOT NULL RETURN k.uid AS uid, k.work_name AS wn"))
    for r in rows:
        s.run("MATCH (k:KnowledgeChunk {uid:$uid}) SET k.work_name_norm=$wf", uid=r["uid"], wf=fold(r["wn"]))
    w=list(s.run("MATCH (w:LiteraryWork) RETURN w.name AS name"))
    for x in w:
        s.run("MATCH (w:LiteraryWork {name:$n}) SET w.name_norm=$f", n=x["name"], f=fold(x["name"]))
    print(f"work_name_norm set on {len(rows)} chunks + {len(w)} LiteraryWork")
drv.close()
