# -*- coding: utf-8 -*-
"""Bổ sung alias BIẾN THỂ TÊN cho mọi thẻ verified (data-only, reversible qua batch):
  - bỏ định ngữ trong ngoặc:  'Kế hoạch Nava (7/1953)' -> 'ke hoach nava'
  - bỏ phần sau ' - ' / ' – ': 'Trần Phú - Tổng Bí thư đầu tiên' -> 'tran phu'
  - bỏ tiền tố loại chung:     'Cuộc/Phong trào/Chiến dịch/Cuộc khởi nghĩa ...'
Chỉ thêm alias có >=8 ký tự và >=2 token (tránh alias rác gây khớp bậy)."""
import os, re, unicodedata
from neo4j import GraphDatabase

BATCH = "alias_variants_2026_08_03"
drv = GraphDatabase.driver(os.getenv("EDU_NEO4J_URI", "bolt://localhost:7688"),
                           auth=(os.getenv("EDU_NEO4J_USER", "neo4j"), os.environ["EDU_NEO4J_PASS"]))

def fold(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").replace("đ", "d")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s)).strip()

PREFIX = ["cuoc khoi nghia ", "cuoc khang chien ", "cuoc cach mang ", "cuoc chien tranh ",
          "cuoc tien cong ", "phong trao ", "chien dich ", "chien thang ", "khoi nghia ",
          "hiep dinh ", "ke hoach ", "cuoc "]

def variants(name):
    out = set()
    base = re.sub(r"\s*\(.*?\)\s*", " ", name or "").strip()          # bỏ ngoặc
    out.add(fold(base))
    out.add(fold(re.split(r"\s+[-–]\s+", base)[0]))                    # bỏ phần sau dấu gạch
    for v in list(out):
        for p in PREFIX:
            if v.startswith(p) and len(v) - len(p) >= 8:
                out.add(v[len(p):])
    return {v for v in out if len(v) >= 8 and len(v.split()) >= 2}

with drv.session() as s:
    evs = s.run("""MATCH (h:HistEvent) WHERE h.verified=true
                   RETURN elementId(h) AS e, h.canonical_name AS n""").data()
    added = 0
    for ev in evs:
        for v in variants(ev["n"]):
            r = s.run("""MERGE (a:HistAlias {value_norm:$v})
                         ON CREATE SET a.ingest_batch=$b
                         WITH a MATCH (h) WHERE elementId(h)=$e
                         MERGE (a)-[rel:ALIAS_OF]->(h)
                         RETURN 1 AS ok""", v=v, e=ev["e"], b=BATCH).single()
            added += 1
    print(f"thẻ verified: {len(evs)} | lượt gắn alias biến thể: {added}")
    print("alias tổng:", s.run("MATCH (a:HistAlias) RETURN count(*) AS c").single()["c"])
    print(f"Rollback (chỉ alias mới): MATCH (a:HistAlias {{ingest_batch:'{BATCH}'}}) DETACH DELETE a")
