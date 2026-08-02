# -*- coding: utf-8 -*-
"""Test tầng fact-node KHÔNG cần server/GPU: mô phỏng ĐÚNG logic query_hist_event
(alias-longest -> year-filter -> sibling-guard -> token-subset fallback) trực tiếp trên Neo4j.
Dùng để đo battery sau khi nạp thẻ verified mà không phải bật canary."""
import json, os, re, sys, unicodedata
from neo4j import GraphDatabase

HERE = os.path.dirname(os.path.abspath(__file__))
drv = GraphDatabase.driver(os.getenv("EDU_NEO4J_URI", "bolt://localhost:7688"),
                           auth=(os.getenv("EDU_NEO4J_USER", "neo4j"), os.environ["EDU_NEO4J_PASS"]))

def hfold(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").replace("đ", "d")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s)).strip()

_NUMW = {"không":0,"linh":0,"một":1,"mốt":1,"hai":2,"ba":3,"bốn":4,"tư":4,"năm":5,"lăm":5,
         "sáu":6,"bảy":7,"bẩy":7,"tám":8,"chín":9,"mười":10}
def spoken_years(q):
    out=[]; toks=[t for t in re.split(r"[^\wÀ-ỹ]+", (q or "").lower()) if t]; digs=[]
    for i,t in enumerate(toks):
        if t in ("năm","nam") and i+1<len(toks) and toks[i+1] in _NUMW:
            if len(digs)==4: out.append(int("".join(digs)))
            elif len(digs)==2: out.append(1900+int("".join(digs)))
            digs=[]; continue
        if t in _NUMW and _NUMW[t]<=9: digs.append(str(_NUMW[t]))
        else:
            if len(digs)==4: out.append(int("".join(digs)))
            elif len(digs)==2: out.append(1900+int("".join(digs)))
            digs=[]
    if len(digs)==4: out.append(int("".join(digs)))
    elif len(digs)==2: out.append(1900+int("".join(digs)))
    return [y for y in out if 100<=y<=2030]

def qyears(q):
    return sorted(set([int(m) for m in re.findall(r"\b(1[0-9]{3}|20[0-2][0-9])\b", q or "")] + spoken_years(q)))

Q_MAIN = """MATCH (a:HistAlias)-[:ALIAS_OF]->(h:HistEvent)
WHERE h.verified=true AND (' '+$qf+' ') CONTAINS (' '+a.value_norm+' ')
RETURN a.value_norm AS alias, h.canonical_name AS name, h.name_norm AS nn, h.year AS year,
       h.date_start AS ds, h.date_end AS de, h.place AS place, h.actors AS actors,
       h.summary AS summary, h.facts AS facts, h.traps AS traps, h.grade AS grade
ORDER BY size(a.value_norm) DESC LIMIT 25"""
Q_ALL = """MATCH (a:HistAlias)-[:ALIAS_OF]->(h:HistEvent)
WHERE h.verified=true AND size(a.value_norm)>=8
RETURN a.value_norm AS alias, h.canonical_name AS name, h.name_norm AS nn, h.year AS year,
       h.date_start AS ds, h.date_end AS de, h.place AS place, h.actors AS actors,
       h.summary AS summary, h.facts AS facts, h.traps AS traps, h.grade AS grade"""
Q_SIB = """MATCH (a:HistAlias)-[:ALIAS_OF]->(h:HistEvent)
WHERE h.verified=true AND a.value_norm STARTS WITH $base AND a.value_norm<>$base
  AND h.name_norm<>$nn
  AND h.year IS NOT NULL AND h.year<>-99999 AND ($y IS NULL OR abs(h.year-$y)>1)
RETURN DISTINCT h.canonical_name AS name, h.year AS year LIMIT 4"""

def lookup(sess, q):
    qf = hfold(q); ys = qyears(q)
    rows = sess.run(Q_MAIN, qf=qf).data()
    if not rows:
        cand = sess.run(Q_ALL).data(); qt = qf.split()
        def sub(a):
            at=a.split()
            if len(at)<3: return False   # >=3 token
            j=0; first=None; last=None
            for i,t in enumerate(qt):
                if j<len(at) and t==at[j]:
                    if first is None: first=i
                    last=i; j+=1
            if j!=len(at): return False
            # các token của alias phải NẰM SÁT nhau: tối đa 2 từ lạ chèn vào
            return (last-first+1) - len(at) <= 2
        rows = sorted([r for r in cand if sub(r["alias"])], key=lambda r:-len(r["alias"]))
        if not rows: return None, "MISS"
    best = len(rows[0]["alias"])
    top = [r for r in rows if len(r["alias"])>=best]
    # GỘP TRÙNG-LẶP-DỮ-LIỆU: cùng sự kiện bị tách nhiều node (biến thể tên / lặp theo lớp).
    # Chỉ coi là NHẬP NHẰNG THẬT khi các ứng viên có NĂM XÁC ĐỊNH KHÁC NHAU.
    def _y(r):
        y = r.get("year")
        return None if y in (None, -99999) else y
    ys_top = {_y(r) for r in top if _y(r) is not None}
    if len(top) > 1 and len(ys_top) <= 1:
        top = [max(top, key=lambda r: (len(r.get("facts") or []), len(r.get("summary") or "")))]
    if ys:
        yf=[r for r in top if r.get("year") and any(abs(r["year"]-y)<=1 for y in ys)]
        if yf: top=yf
        else:
            alt=sess.run("""MATCH (a:HistAlias)-[:ALIAS_OF]->(h:HistEvent)
                WHERE h.verified=true AND a.value_norm STARTS WITH $b AND h.year IS NOT NULL
                RETURN h.canonical_name AS name, h.year AS year, h.date_start AS ds, h.date_end AS de,
                       h.place AS place, h.actors AS actors, h.summary AS summary, h.facts AS facts,
                       h.traps AS traps, h.grade AS grade, h.name_norm AS nn, a.value_norm AS alias LIMIT 20""",
                b=top[0]["alias"]).data()
            ok=[r for r in alt if any(abs(r["year"]-y)<=1 for y in ys)]
            if ok: top=ok[:1]
            else: return None, "MISS-năm-lệch"
    if len(top)==1 and not ys:
        _yy = top[0].get("year")
        if _yy == -99999: _yy = None
        sib = sess.run(Q_SIB, base=top[0]["alias"], nn=top[0]["nn"], y=_yy).data()
        if sib: return top[0], "CLARIFY"
    if len(top)!=1: return None, "AMBIG"
    return top[0], "FACT"

def ctx_of(r):
    p=[r["name"]]
    if r.get("ds"): p.append(f"Thời gian: {r['ds']}" + (f" đến {r['de']}" if r.get("de") else ""))
    elif r.get("year"): p.append(f"Năm: {r['year']}")
    if r.get("place"): p.append(f"Địa điểm: {r['place']}")
    if r.get("actors"): p.append(", ".join(r["actors"][:6]))
    if r.get("summary"): p.append(r["summary"])
    if r.get("facts"): p.append("\n".join(r["facts"]))
    return "\n".join(p)

bat = json.load(open(f"{HERE}/hist_battery.json", encoding="utf-8"))
res=[]
with drv.session() as s:
    for t in bat:
        r, kind = lookup(s, t["q"])
        if r is None:
            res.append((t["id"], kind, "")); continue
        c = ctx_of(r).lower()
        has_e = any(e.lower() in c for e in t["expect"])
        head = c.split("\n")
        head = "\n".join(head[:4]).lower()
        has_f = any(f in head for f in t["forbid"]) if t["forbid"] else False
        v = "PASS" if (has_e and not has_f) else ("TRAP" if has_f else "NOFACT")
        res.append((t["id"], v if kind=="FACT" else f"{kind}/{v}", r["name"]))

from collections import Counter
p=sum(1 for _,v,_ in res if v=="PASS")
print(f"=== FACT-NODE (offline, {len(res)} câu) — PASS {p}/{len(res)} ===")
print("  ", dict(Counter(v for _,v,_ in res)))
print("  -- không PASS --")
for i,v,n in res:
    if v!="PASS": print(f"   {v:14s} {i:20s} {n[:40]}")
