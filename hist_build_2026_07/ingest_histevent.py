# -*- coding: utf-8 -*-
"""Ingest :HistEvent + :Alias theo thiết kế research.
- gold_cards.json  -> verified=true , source_tier='gold' (giáo viên xác nhận qua checklist)
- cards_gated.json -> verified=false, source_tier='web'|'soanbai' (CHỜ agent verify, KHÔNG serve)
Reversible: ingest_batch + backup elementId. Tạo RANGE index theo design."""
import json, re, sys, unicodedata
import os
from neo4j import GraphDatabase

BATCH = "histevent_v1_2026_07_26"
SOAN = ("loigiaihay", "vietjack", "vndoc", "tech12h", "hoc247", "hoidap", "lazi", "tailieu")
GOOD = ("wikipedia", "wikidata", "nguoikesu", ".gov.vn", "baotang", "britannica", "history.com")

def fold(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").replace("đ", "d")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s)).strip()

def tier_of(card):
    ss = [s.lower() for s in (card.get("sources") or []) if isinstance(s, str)]
    if any("teacher_verified" in s for s in ss): return "gold"
    if any(any(k in s for k in GOOD) for s in ss): return "web"
    if any(any(k in s for k in SOAN) for s in ss): return "soanbai"
    return "unknown"

gold = json.load(open("/tmp/gold_cards.json"))
raw = json.load(open("/tmp/cards_gated.json"))
for c in gold: c["_verified"] = True
for c in raw: c["_verified"] = False
allc = gold + raw

drv = GraphDatabase.driver(os.getenv("EDU_NEO4J_URI", "bolt://localhost:7688"),
                          auth=(os.getenv("EDU_NEO4J_USER", "neo4j"), os.environ["EDU_NEO4J_PASS"]))
created, alias_n, skipped = [], 0, 0

with drv.session() as s:
    for stmt in [
        "CREATE RANGE INDEX he_norm IF NOT EXISTS FOR (h:HistEvent) ON (h.name_norm)",
        "CREATE RANGE INDEX he_year IF NOT EXISTS FOR (h:HistEvent) ON (h.year)",
        "CREATE RANGE INDEX he_ver  IF NOT EXISTS FOR (h:HistEvent) ON (h.verified)",
        "CREATE RANGE INDEX al_norm IF NOT EXISTS FOR (a:HistAlias) ON (a.value_norm)",
    ]:
        try: s.run(stmt)
        except Exception as e: print("[idx]", e)

    for c in allc:
        nn = fold(c["name"])
        if not nn: skipped += 1; continue
        grade = c.get("grade") or c.get("_grade")
        r = s.run("""
            MERGE (h:HistEvent {name_norm:$nn, year:coalesce($y,-99999)})
            ON CREATE SET h.canonical_name=$name, h.kind=$kind, h.date_start=$ds, h.date_end=$de,
                h.place=$place, h.actors=$actors, h.summary=$summary, h.facts=$facts, h.traps=$traps,
                h.topic_title=$topic, h.grade=$grade, h.sources=$sources,
                h.subject_code='lich_su', h.verified=$ver, h.source_tier=$tier,
                h.ingest_batch=$batch, h._new=true
            ON MATCH SET h._new=false
            RETURN elementId(h) AS e, h._new AS isnew
        """, nn=nn, y=c.get("year"), name=c["name"], kind=c.get("kind", "event"),
             ds=c.get("date_start"), de=c.get("date_end"), place=c.get("place"),
             actors=c.get("actors") or [], summary=c.get("summary", ""),
             facts=c.get("facts") or [], traps=c.get("traps") or [],
             topic=c.get("topic_title", ""), grade=grade, sources=c.get("sources") or [],
             ver=bool(c["_verified"]), tier=tier_of(c), batch=BATCH).single()
        eid = r["e"]
        if r["isnew"]: created.append(eid)
        s.run("MATCH (h) WHERE elementId(h)=$e REMOVE h._new", e=eid)
        # aliases -> node riêng (index-seek, không quét mảng)
        for a in set([nn] + [fold(x) for x in (c.get("aliases") or [])]):
            if not a: continue
            s.run("""MERGE (al:HistAlias {value_norm:$a})
                     ON CREATE SET al.ingest_batch=$batch
                     WITH al MATCH (h) WHERE elementId(h)=$e
                     MERGE (al)-[:ALIAS_OF]->(h)""", a=a, e=eid, batch=BATCH)
            alias_n += 1

    # nối HistEvent -> HistLesson theo topic_title (khớp title_norm)
    linked = s.run("""
        MATCH (h:HistEvent {ingest_batch:$b}) WHERE h.topic_title IS NOT NULL AND h.topic_title<>''
        MATCH (l:HistLesson) WHERE l.grade=h.grade AND l.title_norm=$dummy
        RETURN count(*) AS c""", b=BATCH, dummy="__never__").single()["c"]

print(f"CREATED HistEvent: {len(created)} | alias-links: {alias_n} | skip: {skipped}")
json.dump({"batch": BATCH, "elementIds": created},
          open("/home/namnx/Ptalk_project/CloudPTalk/recite_cleanup_2026_07_09/histevent_ingest_2026_07_26.json", "w"))
print("Rollback: MATCH (n) WHERE n.ingest_batch='%s' DETACH DELETE n" % BATCH)

with drv.session() as s:
    print("\n=== THỐNG KÊ ===")
    for x in s.run("""MATCH (h:HistEvent) RETURN h.verified AS v, h.source_tier AS t, count(*) AS c
                      ORDER BY v DESC, c DESC"""):
        print(f"  verified={x['v']!s:5s} tier={x['t']!s:8s} {x['c']}")
    for x in s.run("MATCH (h:HistEvent) RETURN h.grade AS g, count(*) AS c ORDER BY g"):
        print(f"  L{x['g']}: {x['c']}")
    print("  alias nodes:", s.run("MATCH (a:HistAlias) RETURN count(*) AS c").single()["c"])
