# -*- coding: utf-8 -*-
"""Nối (:HistLesson)-[:HAS_EVENT]->(:HistEvent) theo topic_title <-> title_norm.
Khớp 3 mức, dừng ở mức khớp được (tất định, không fuzzy mờ):
  1. cùng lớp + title_norm == fold(topic_title)
  2. cùng lớp + một bên chứa bên kia (>=12 ký tự, tránh khớp bậy)
  3. cùng lớp + trùng >=70% token (ngưỡng cao)
Data-only, reversible: cạnh gắn tag batch."""
import os, re, sys, unicodedata
from collections import Counter
from neo4j import GraphDatabase

BATCH = os.getenv("HASEVENT_BATCH", "hasevent_v1_2026_08_03")
drv = GraphDatabase.driver(os.getenv("EDU_NEO4J_URI", "bolt://localhost:7688"),
                           auth=(os.getenv("EDU_NEO4J_USER", "neo4j"), os.environ["EDU_NEO4J_PASS"]))

def fold(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").replace("đ", "d")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s)).strip()

STOP = {"bai", "va", "cua", "the", "tu", "den", "nam", "trong", "cac", "o", "voi", "ve", "mot"}
def toks(s): return {t for t in fold(s).split() if t not in STOP and len(t) > 1}

with drv.session() as s:
    lessons = s.run("""MATCH (l:HistLesson)
                       RETURN elementId(l) AS e, l.grade AS g, l.title_norm AS tn, l.title AS t""").data()
    events = s.run("""MATCH (h:HistEvent) WHERE h.verified=true AND h.topic_title IS NOT NULL
                      AND h.topic_title <> ''
                      RETURN elementId(h) AS e, h.grade AS g, h.grades AS gs,
                             h.topic_title AS tt, h.canonical_name AS n""").data()
    print(f"bài: {len(lessons)} | thẻ verified có topic: {len(events)}")

    bygrade = {}
    for l in lessons:
        bygrade.setdefault(l["g"], []).append(l)

    stat = Counter(); pairs = []
    for ev in events:
        # thẻ được GỘP từ nhiều lớp -> khớp RIÊNG trong từng lớp có dạy (h.grades),
        # không chỉ lớp nhỏ nhất; thẻ cũ không có grades thì dùng h.grade như trước.
        gl = [g for g in (ev.get("gs") or []) if g] or [ev["g"]]
        got = False
        for g in gl:
            cands = bygrade.get(g, [])
            if not cands:
                continue
            tf = fold(ev["tt"])
            hit = [l for l in cands if l["tn"] == tf]
            lvl = "exact"
            if not hit and len(tf) >= 12:
                hit = [l for l in cands if (tf in l["tn"] or l["tn"] in tf)]
                lvl = "chứa"
            if not hit:
                et = toks(ev["tt"])
                if et:
                    scored = []
                    for l in cands:
                        lt = toks(l["t"] or l["tn"])
                        if not lt:
                            continue
                        ov = len(et & lt) / max(1, min(len(et), len(lt)))
                        if ov >= 0.70:
                            scored.append((ov, l))
                    if scored:
                        scored.sort(key=lambda x: -x[0])
                        hit = [scored[0][1]]
                        lvl = "token70"
            if not hit:
                continue
            stat[lvl] += 1
            got = True
            for l in hit[:3]:
                pairs.append((l["e"], ev["e"]))
        if not got:
            stat["không khớp bài nào"] += 1

    for le, he in pairs:
        s.run("""MATCH (l) WHERE elementId(l)=$le MATCH (h) WHERE elementId(h)=$he
                 MERGE (l)-[r:HAS_EVENT]->(h) ON CREATE SET r.batch=$b""", le=le, he=he, b=BATCH)

    print("mức khớp:", dict(stat))
    print(f"cạnh HAS_EVENT tạo: {len(pairs)}")
    print(f"Rollback: MATCH ()-[r:HAS_EVENT {{batch:'{BATCH}'}}]->() DELETE r")

    n = s.run("MATCH ()-[r:HAS_EVENT]->() RETURN count(r) AS c").single()["c"]
    print(f"tổng HAS_EVENT: {n}")
    cov = s.run("""MATCH (l:HistLesson) WHERE EXISTS { (l)-[:HAS_EVENT]->() }
                   RETURN l.grade AS g, count(DISTINCT l) AS c ORDER BY g""").data()
    tot = s.run("MATCH (l:HistLesson) RETURN l.grade AS g, count(*) AS c ORDER BY g").data()
    tm = {r["g"]: r["c"] for r in tot}
    print("bài có ít nhất 1 thẻ:", "  ".join(f"L{r['g']}:{r['c']}/{tm.get(r['g'],0)}" for r in cov))
