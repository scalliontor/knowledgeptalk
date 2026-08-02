# -*- coding: utf-8 -*-
"""Dọn alias rác + gộp thẻ trùng (data-only, reversible qua tag).
(1) XOÁ alias quá ngắn (<4 ký tự) hoặc là từ phổ thông -> nguyên nhân 'un' khớp trong 'xây dựng'
(2) GỘP thẻ trùng: cùng name_norm, một bản year=null (-99999) và một bản year thật
    -> giữ bản có year, chuyển alias sang, xoá bản null (ưu tiên GIỮ tier=gold)
Rollback: các node bị xoá được ghi ra file trước khi xoá."""
import json, os, sys
from neo4j import GraphDatabase

HERE = os.path.dirname(os.path.abspath(__file__))
drv = GraphDatabase.driver(os.getenv("EDU_NEO4J_URI", "bolt://localhost:7688"),
                           auth=(os.getenv("EDU_NEO4J_USER", "neo4j"), os.environ["EDU_NEO4J_PASS"]))

STOP = {"un", "eu", "mi", "my", "ta", "ho", "le", "ly", "tu", "vn", "usa", "anh", "phap", "duc",
        "nga", "mo", "co", "cu", "ba", "nam", "bac", "trung", "dong", "tay", "vua", "dang"}

with drv.session() as s:
    print("=== (1) alias rác ===")
    bad = s.run("""MATCH (a:HistAlias)
                   WHERE size(a.value_norm) < 4 OR a.value_norm IN $stop
                   RETURN a.value_norm AS v, COUNT{ (a)-[:ALIAS_OF]->() } AS deg
                   ORDER BY deg DESC""", stop=sorted(STOP)).data()
    for b in bad[:15]:
        print(f"  xoá alias {b['v']!r} (trỏ {b['deg']} thẻ)")
    json.dump(bad, open(f"{HERE}/deleted_aliases_backup.json", "w"), ensure_ascii=False)
    n = s.run("""MATCH (a:HistAlias)
                 WHERE size(a.value_norm) < 4 OR a.value_norm IN $stop
                 DETACH DELETE a RETURN count(*) AS c""", stop=sorted(STOP)).single()["c"]
    print(f"  -> đã xoá {n} alias rác (backup: deleted_aliases_backup.json)")

    print("\n=== (2) thẻ trùng name_norm: bản year=null vs bản có year ===")
    dups = s.run("""MATCH (h:HistEvent)
                    WITH h.name_norm AS nn, collect(h) AS hs
                    WHERE size(hs) > 1
                    RETURN nn, [x IN hs | {e:elementId(x), y:x.year, t:x.source_tier,
                                           nf:size(coalesce(x.facts,[])), g:x.grade}] AS items""").data()
    merged = 0; killed = []
    for d in dups:
        items = d["items"]
        withy = [i for i in items if i["y"] not in (None, -99999)]
        noy = [i for i in items if i["y"] in (None, -99999)]
        if not withy or not noy:
            continue
        # giữ: ưu tiên gold, rồi nhiều facts nhất
        keep = sorted(withy, key=lambda i: (0 if i["t"] == "gold" else 1, -i["nf"]))[0]
        for k in noy:
            s.run("""MATCH (a:HistAlias)-[:ALIAS_OF]->(old) WHERE elementId(old)=$o
                     MATCH (new) WHERE elementId(new)=$n
                     MERGE (a)-[:ALIAS_OF]->(new)""", o=k["e"], n=keep["e"])
            killed.append({"nn": d["nn"], **k})
            s.run("MATCH (x) WHERE elementId(x)=$e DETACH DELETE x", e=k["e"])
            merged += 1
    json.dump(killed, open(f"{HERE}/merged_nodes_backup.json", "w"), ensure_ascii=False)
    print(f"  -> gộp/xoá {merged} thẻ trùng year-null (backup: merged_nodes_backup.json)")

    print("\n=== SAU KHI DỌN ===")
    for x in s.run("""MATCH (h:HistEvent) RETURN h.verified AS v, h.source_tier AS t, count(*) AS c
                      ORDER BY v DESC, c DESC"""):
        print(f"  verified={x['v']!s:5s} tier={str(x['t']):<18} {x['c']}")
    print("  alias:", s.run("MATCH (a:HistAlias) RETURN count(*) AS c").single()["c"])
    rows = s.run("MATCH (h:HistEvent {verified:true}) RETURN h.grade AS g, count(*) AS c ORDER BY g").data()
    print("  PHỤC VỤ theo lớp:", "  ".join(f"L{r['g']}:{r['c']}" for r in rows))
