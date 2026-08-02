# -*- coding: utf-8 -*-
import os, re, unicodedata
from neo4j import GraphDatabase
d = GraphDatabase.driver("bolt://localhost:7688", auth=("neo4j", os.environ["EDU_NEO4J_PASS"]))

def hf(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").replace("đ", "d")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s)).strip()

QS = ["Công xã Pa-ri diễn ra năm nào", "Nhà Trần được thành lập năm nào",
      "kế hoạch Nava gồm mấy bước", "Tổng bí thư đầu tiên của Đảng Cộng sản Việt Nam là ai"]
with d.session() as s:
    for q in QS:
        rows = s.run("""MATCH (a:HistAlias)-[:ALIAS_OF]->(h:HistEvent)
            WHERE h.verified=true AND $qf CONTAINS a.value_norm
            RETURN a.value_norm AS al, h.canonical_name AS n, h.year AS y, h.grade AS g
            ORDER BY size(a.value_norm) DESC LIMIT 8""", qf=hf(q)).data()
        print("Q:", q)
        for r in rows:
            print("   [%2d] %-30s -> %-40s y=%s L%s" % (len(r["al"]), r["al"], str(r["n"])[:40], r["y"], r["g"]))
        print()
