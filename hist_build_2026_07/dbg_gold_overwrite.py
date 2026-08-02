# -*- coding: utf-8 -*-
"""Kiểm 2 nghi vấn: (1) thẻ GOLD bị thẻ máy ghi đè? (2) alias nào khiến 'chùa thời Lý' -> 'Liên hợp quốc'?"""
import os, re, unicodedata
from neo4j import GraphDatabase
d = GraphDatabase.driver("bolt://localhost:7688", auth=("neo4j", os.environ["EDU_NEO4J_PASS"]))

def hf(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").replace("đ", "d")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s)).strip()

GOLD_NAMES = ["Vua Dục Đức", "Trần Phú", "Nguyễn Hiền", "Nguyễn Trung Trực", "Kế hoạch Na-va",
              "Tạm ước Việt - Pháp", "Hồng quân Liên Xô", "Chiến dịch Điện Biên Phủ trên không"]
with d.session() as s:
    print("=== (1) Thẻ GOLD giờ ra sao ===")
    for n in GOLD_NAMES:
        rows = s.run("""MATCH (h:HistEvent) WHERE h.name_norm=$nn
                        RETURN h.canonical_name AS n, h.year AS y, h.source_tier AS t,
                               h.ingest_batch AS b, h.grade AS g""", nn=hf(n)).data()
        if not rows:
            print(f"  [MẤT] {n}")
        for r in rows:
            print(f"  {r['n'][:42]:<44} y={str(r['y']):<7} tier={str(r['t']):<17} batch={str(r['b'])[-12:]}")

    print("\n=== (2) alias khớp câu 'chùa thời Lý' ===")
    qf = hf("Vì sao thời Lý chùa được xây dựng nhiều")
    for r in s.run("""MATCH (a:HistAlias)-[:ALIAS_OF]->(h:HistEvent)
                      WHERE h.verified=true AND $qf CONTAINS a.value_norm
                      RETURN a.value_norm AS al, h.canonical_name AS n
                      ORDER BY size(a.value_norm) DESC LIMIT 6""", qf=qf).data():
        print(f"  [{len(r['al']):2d}] {r['al']:<24} -> {r['n'][:44]}")
    print("  (câu fold:", qf, ")")

    print("\n=== (3) alias RÁC: quá ngắn / quá chung ===")
    for r in s.run("""MATCH (a:HistAlias)-[:ALIAS_OF]->(h:HistEvent)
                      WITH a, count(h) AS deg WHERE deg >= 4
                      RETURN a.value_norm AS al, deg ORDER BY deg DESC LIMIT 12""").data():
        print(f"  {r['al']:<34} trỏ tới {r['deg']} thẻ")
