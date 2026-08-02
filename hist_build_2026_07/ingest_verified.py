# -*- coding: utf-8 -*-
"""Nạp thẻ ĐÃ VERIFY vào :HistEvent với verified=true (được phục vụ).
- Nguồn: cards_v_gated.json (đã qua gate tất định)
- Thẻ trùng tên KHÁC NĂM -> tự thêm định ngữ năm vào canonical_name để phân biệt
- Thẻ trùng tên CÙNG NĂM -> gộp (giữ bản nhiều facts hơn)
- Alias -> node :HistAlias riêng (index-seek)
- Reversible: ingest_batch + backup elementId
Creds qua env EDU_NEO4J_PASS."""
import json, os, re, sys, unicodedata
from collections import defaultdict
from neo4j import GraphDatabase

BATCH = "histevent_verified_2026_08_02"
HERE = os.path.dirname(os.path.abspath(__file__))
URI = os.getenv("EDU_NEO4J_URI", "bolt://localhost:7688")
PASS = os.getenv("EDU_NEO4J_PASS")
if not PASS:
    sys.exit("Thiếu EDU_NEO4J_PASS")

SOAN = ("loigiaihay", "vietjack", "vndoc", "tech12h", "hoc247", "hoidap", "lazi", "tailieu")
GOOD = ("wikipedia", "wikidata", "nguoikesu", ".gov.vn", "baotang", "britannica", "history.com", "dangcongsan", "nhandan")

def fold(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").replace("đ", "d")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s)).strip()

def tier_of(c):
    ss = [s.lower() for s in (c.get("sources") or []) if isinstance(s, str)]
    if any(any(k in s for k in GOOD) for s in ss): return "web_verified"
    if any(any(k in s for k in SOAN) for s in ss): return "soanbai_verified"
    return "unknown_verified"

cards = json.load(open(f"{HERE}/cards_v_gated.json", encoding="utf-8"))
print(f"vào: {len(cards)} thẻ đã verify + qua gate")

# ── gộp/phân biệt trùng tên ──
by = defaultdict(list)
for c in cards:
    by[fold(c["name"])].append(c)
final, renamed, merged = [], 0, 0
for nn, group in by.items():
    if len(group) == 1:
        final.append(group[0]); continue
    years = {c.get("year") for c in group}
    if len(years) == 1:
        # cùng năm -> gộp, giữ bản nhiều facts nhất
        best = max(group, key=lambda c: len(c.get("facts") or []))
        al = set()
        for c in group: al |= set(c.get("aliases") or [])
        best["aliases"] = sorted(al)
        final.append(best); merged += len(group) - 1
    else:
        # KHÁC NĂM -> thêm định ngữ năm để phân biệt (chống trả sai thẻ)
        for c in group:
            y = c.get("year")
            if y is not None and str(y) not in c["name"]:
                c["aliases"] = sorted(set((c.get("aliases") or []) + [c["name"]]))
                c["name"] = f"{c['name']} ({y})"
                renamed += 1
            final.append(c)
print(f"  gộp trùng cùng-năm: {merged} | thêm định ngữ năm: {renamed} | còn {len(final)} thẻ")

drv = GraphDatabase.driver(URI, auth=(os.getenv("EDU_NEO4J_USER", "neo4j"), PASS))
created, alias_n = [], 0
with drv.session() as s:
    for c in final:
        nn = fold(c["name"])
        if not nn: continue
        g = c.get("grade") or c.get("_grade")
        r = s.run("""
            MERGE (h:HistEvent {name_norm:$nn, year:coalesce($y,-99999)})
            ON CREATE SET h._new=true
            SET h.canonical_name=$name, h.kind=$kind, h.date_start=$ds, h.date_end=$de,
                h.place=$place, h.actors=$actors, h.summary=$summary, h.facts=$facts,
                h.traps=$traps, h.topic_title=$topic, h.grade=$g, h.sources=$sources,
                h.subject_code='lich_su', h.verified=true, h.source_tier=$tier,
                h.ingest_batch=$batch, h.fixed_notes=$fixed
            RETURN elementId(h) AS e, coalesce(h._new,false) AS isnew
        """, nn=nn, y=c.get("year"), name=c["name"], kind=c.get("kind", "event"),
             ds=c.get("date_start"), de=c.get("date_end"), place=c.get("place"),
             actors=c.get("actors") or [], summary=c.get("summary", ""),
             facts=c.get("facts") or [], traps=c.get("traps") or [],
             topic=c.get("topic_title", ""), g=g, sources=c.get("sources") or [],
             tier=tier_of(c), batch=BATCH, fixed=c.get("fixed") or []).single()
        eid = r["e"]
        if r["isnew"]: created.append(eid)
        s.run("MATCH (h) WHERE elementId(h)=$e REMOVE h._new", e=eid)
        for a in set([nn] + [fold(x) for x in (c.get("aliases") or [])]):
            if not a or len(a) < 3: continue
            s.run("""MERGE (al:HistAlias {value_norm:$a})
                     ON CREATE SET al.ingest_batch=$b
                     WITH al MATCH (h) WHERE elementId(h)=$e
                     MERGE (al)-[:ALIAS_OF]->(h)""", a=a, e=eid, b=BATCH)
            alias_n += 1

json.dump({"batch": BATCH, "elementIds": created}, open(f"{HERE}/ingest_verified_backup.json", "w"))
print(f"CREATED {len(created)} | alias-links {alias_n}")
print(f"Rollback: MATCH (n) WHERE n.ingest_batch='{BATCH}' DETACH DELETE n")

with drv.session() as s:
    print("\n=== HistEvent sau khi nạp ===")
    for x in s.run("""MATCH (h:HistEvent) RETURN h.verified AS v, h.source_tier AS t, count(*) AS c
                      ORDER BY v DESC, c DESC"""):
        print(f"  verified={x['v']!s:5s} tier={str(x['t']):<18} {x['c']}")
    rows = s.run("MATCH (h:HistEvent {verified:true}) RETURN h.grade AS g, count(*) AS c ORDER BY g").data()
    print("  PHỤC VỤ theo lớp:", "  ".join(f"L{r['g']}:{r['c']}" for r in rows))
    print("  alias nodes:", s.run("MATCH (a:HistAlias) RETURN count(*) AS c").single()["c"])
