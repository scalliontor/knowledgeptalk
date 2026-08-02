# -*- coding: utf-8 -*-
"""TEST THEO KIẾN THỨC TỪNG BÀI HỌC (offline, không cần server/GPU).
Với mỗi (:HistLesson)-[:HAS_EVENT]->(:HistEvent verified):
  - sinh câu hỏi TẤT ĐỊNH từ field thẻ (năm / nơi / nhân vật / định danh)
  - tra lại bằng ĐÚNG logic fact-node (alias-longest + year + sibling-guard + fallback)
  - chấm: có lấy ra ĐÚNG thẻ gốc không (so theo canonical_name)
Báo cáo THEO TỪNG BÀI giống checklist: ✓ đủ / ~ một phần / ✗ hỏng.
"""
import os, re, sys, unicodedata
from collections import defaultdict, Counter
from neo4j import GraphDatabase

drv = GraphDatabase.driver(os.getenv("EDU_NEO4J_URI", "bolt://localhost:7688"),
                           auth=(os.getenv("EDU_NEO4J_USER", "neo4j"), os.environ["EDU_NEO4J_PASS"]))
GRADE = int(sys.argv[1]) if len(sys.argv) > 1 else None

def hfold(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").replace("đ", "d")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s)).strip()

Q_MAIN = """MATCH (a:HistAlias)-[:ALIAS_OF]->(h:HistEvent)
WHERE h.verified=true AND (' '+$qf+' ') CONTAINS (' '+a.value_norm+' ')
RETURN a.value_norm AS alias, h.canonical_name AS name, h.name_norm AS nn, h.year AS year,
       h.facts AS facts, h.summary AS summary
ORDER BY size(a.value_norm) DESC LIMIT 25"""
Q_SIB = """MATCH (a:HistAlias)-[:ALIAS_OF]->(h:HistEvent)
WHERE h.verified=true AND a.value_norm STARTS WITH $base AND a.value_norm<>$base
  AND h.name_norm<>$nn AND h.year IS NOT NULL AND h.year<>-99999
  AND ($y IS NULL OR abs(h.year-$y)>1)
RETURN DISTINCT h.canonical_name AS name LIMIT 3"""

def qyears(q):
    return sorted({int(m) for m in re.findall(r"\b(1[0-9]{3}|20[0-2][0-9])\b", q or "")})

def lookup(sess, q):
    qf = hfold(q); ys = qyears(q)
    rows = sess.run(Q_MAIN, qf=qf).data()
    if not rows: return None, "MISS"
    best = len(rows[0]["alias"]); top = [r for r in rows if len(r["alias"]) >= best]
    _y = lambda r: None if r.get("year") in (None, -99999) else r["year"]
    ys_top = {_y(r) for r in top if _y(r) is not None}
    if len(top) > 1 and len(ys_top) <= 1:
        top = [max(top, key=lambda r: (len(r.get("facts") or []), len(r.get("summary") or "")))]
    if ys:
        yf = [r for r in top if _y(r) and any(abs(r["year"] - y) <= 1 for y in ys)]
        if yf: top = yf
    if len(top) == 1 and not ys:
        sib = sess.run(Q_SIB, base=top[0]["alias"], nn=top[0]["nn"], y=_y(top[0])).data()
        if sib: return top[0], "CLARIFY"
    if len(top) != 1: return None, "AMBIG"
    return top[0], "OK"

def gen(card):
    """Câu hỏi tất định từ thẻ -> [(câu, loại)]"""
    n = card["name"]; out = []
    base = re.sub(r"\s*\(.*?\)\s*", " ", n).strip()   # bỏ định ngữ trong ngoặc để hỏi tự nhiên
    if card.get("year") not in (None, -99999):
        out.append((f"{base} diễn ra năm nào", "năm"))
    if card.get("place"):
        out.append((f"{base} diễn ra ở đâu", "nơi"))
    if card.get("actors"):
        out.append((f"Ai tham gia {base}", "nhân vật"))
    if not out:
        out.append((f"{base} là gì", "định danh"))
    return out

with drv.session() as s:
    cy = """MATCH (l:HistLesson)-[:HAS_EVENT]->(h:HistEvent {verified:true})
            %s
            RETURN l.grade AS g, coalesce(l.title, l.title_norm) AS lesson,
                   h.canonical_name AS name, h.year AS year, h.place AS place,
                   h.actors AS actors, h.facts AS facts
            ORDER BY l.grade, lesson""" % ("WHERE l.grade=$g" if GRADE else "")
    rows = s.run(cy, g=GRADE).data() if GRADE else s.run(cy).data()
    print(f"[gen] {len(rows)} cặp (bài × thẻ)" + (f" — lớp {GRADE}" if GRADE else ""))

    bylesson = defaultdict(list)
    for r in rows:
        for q, kind in gen(r):
            got, st = lookup(s, q)
            hit = bool(got) and hfold(got["name"]).startswith(hfold(r["name"])[:18])
            bylesson[(r["g"], r["lesson"])].append((kind, st, hit, r["name"]))

print()
print("=== BÁO CÁO THEO TỪNG BÀI ===")
gstat = defaultdict(lambda: [0, 0]); tp = tq = 0
lines = []
for (g, lesson), qs in sorted(bylesson.items()):
    p = sum(1 for _, _, h, _ in qs if h); n = len(qs)
    tp += p; tq += n; gstat[g][0] += p; gstat[g][1] += n
    mark = "✓" if p == n else ("~" if p else "✗")
    bad = ";".join(f"{k}:{st}" for k, st, h, _ in qs if not h)[:44]
    lines.append(f" {mark} L{g:<2} {str(lesson)[:52]:<54} {p}/{n}" + (f"  [{bad}]" if bad else ""))
for ln in lines[:70]: print(ln)
if len(lines) > 70: print(f"   ... còn {len(lines)-70} bài")
print()
print("=== THEO LỚP ===")
for g in sorted(gstat):
    p, n = gstat[g]
    print(f"  L{g:<3} {p}/{n} = {100*p//max(n,1)}%")
print(f"  TỔNG {tp}/{tq} = {100*tp//max(tq,1)}%")
allq = [x for v in bylesson.values() for x in v]
print("  trạng thái:", dict(Counter(st for _, st, _, _ in allq)))
print("  bài đủ ✓:", sum(1 for l in lines if l.strip().startswith("✓")), "/", len(lines))
