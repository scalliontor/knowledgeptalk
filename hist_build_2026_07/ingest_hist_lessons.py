# -*- coding: utf-8 -*-
"""Nạp khung :HistLesson (813 bài SGK Sử lớp 4-12 từ 'Checklist data Ptalk.xlsx').
Idempotent (MERGE theo grade+bo_sach+title_norm). Reversible: ingest_batch tag + backup eid.
Creds qua env: EDU_NEO4J_URI / EDU_NEO4J_USER / EDU_NEO4J_PASS (xem server.txt — KHÔNG hardcode).
Input: ls_items_v2.json (trích từ sheet 'Lịch sử', 8 khối cột)."""
import json, os, re, sys, unicodedata
from neo4j import GraphDatabase

BATCH = "hist_v1_2026_07_26"
URI = os.getenv("EDU_NEO4J_URI", "bolt://localhost:7688")
USER = os.getenv("EDU_NEO4J_USER", "neo4j")
PASS = os.getenv("EDU_NEO4J_PASS")
if not PASS:
    sys.exit("Thiếu EDU_NEO4J_PASS (không hardcode secret — xem server.txt)")

def fold(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").replace("đ", "d")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s)).strip()

def norm_book(b):
    if not b: return None
    t = fold(b)
    if "knt" in t or "ket noi" in t: return "KNTT"
    if "ctst" in t or "chan troi" in t: return "CTST"
    if "canh dieu" in t or t == "cd": return "CD"
    if "cu" in t.split() or "sach cu" in t or "nxbdg" in t or "nxbgd" in t: return "CU"
    return b.strip()

def topic(name):
    m = re.match(r"^bài\s*(\d+)\s*[:\.\-–]?\s*(.*)$", name.strip(), re.I)
    if m and m.group(2).strip():
        return int(m.group(1)), m.group(2).strip()
    return None, name.strip()

items = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "ls_items_v2.json"))
drv = GraphDatabase.driver(URI, auth=(USER, PASS))
created, existed = [], 0
with drv.session() as s:
    for it in items:
        bai, title = topic(it["name"])
        r = s.run("""
            MERGE (l:HistLesson {grade:$g, bo_sach:coalesce($bo,'?'), title_norm:$tn})
            ON CREATE SET l.title=$title, l.title_raw=$raw, l.bai_no=$bai,
                          l.subject_code='lich_su', l.ingest_batch=$batch, l._created=true
            RETURN elementId(l) AS e, l._created AS c
        """, g=it["g"], bo=norm_book(it["book"]), tn=fold(title),
                  title=title, raw=it["name"], bai=bai, batch=BATCH).single()
        if r["c"]:
            created.append(r["e"])
            s.run("MATCH (l) WHERE elementId(l)=$e REMOVE l._created", e=r["e"])
        else:
            existed += 1
print(f"CREATED {len(created)} | skip {existed} | input {len(items)}")
json.dump({"batch": BATCH, "elementIds": created}, open(f"hist_lessons_ingest_backup.json", "w"))
print("Rollback: MATCH (l:HistLesson {ingest_batch:'%s'}) DETACH DELETE l" % BATCH)
