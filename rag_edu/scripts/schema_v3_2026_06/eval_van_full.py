#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Văn eval G6-9, ~500/grade. 4 types: tác phẩm / section / variant / nội dung.
Emulates work-exact retrieval (schema v3 V-C) via Cypher. No canary."""
import re, unicodedata, random, json
from collections import defaultdict
from neo4j import GraphDatabase
drv = GraphDatabase.driver("bolt://localhost:7688", auth=("neo4j","CHANGEME_NEO4J_PASS"))
random.seed(7); TARGET=500

def fold(s):
    s=(s or '').replace('đ','d').replace('Đ','D')
    s=unicodedata.normalize('NFD',s)
    return ''.join(c for c in s if unicodedata.category(c)!='Mn').lower()

SEC_KW={"soan_bai":"đọc hiểu","viet":"viết","noi_nghe":"nói và nghe","thuc_hanh_tieng_viet":"thực hành tiếng Việt"}
VAR_KW={"chi_tiet":"chi tiết","sieu_ngan":"siêu ngắn","ngan_nhat":"ngắn nhất","standard":""}

# ---- anchors: works with their section/variant options (G6-9) ----
def pull():
    A=defaultdict(list)
    with drv.session() as s:
        for r in s.run("""
            MATCH (k:KnowledgeChunk) WHERE k.subject_code='ngu_van' AND k.production_ready=true
              AND k.work_name IS NOT NULL AND toInteger(k.grade)>=6 AND toInteger(k.grade)<=9
            RETURN toInteger(k.grade) AS g, k.bo_sach AS bo, k.work_name AS work,
                   collect(DISTINCT k.section_type) AS secs, collect(DISTINCT k.variant) AS vars
        """):
            d=dict(r)
            if 3<len(d["work"])<70: A[d["g"]].append(d)
    return A

T_TP=["soạn bài {w} lớp {g}","cô ơi giảng bài {w}","{w} {bk}","soạn văn bài {w}","giúp em soạn {w}"]
T_SEC=["{w} phần {sec}","phần {sec} bài {w}","soạn {w} phần {sec}"]
T_VAR=["soạn {w} {var}","{w} bản {var}","cho em {w} {var}"]
T_ND=["{w} nói về gì ạ","phân tích bài {w}","nội dung bài {w} là gì","{w} của tác giả nào"]
BK={"KNTT":"kết nối tri thức","CTST":"chân trời sáng tạo","CD":"cánh diều"}

def gen(g, works):
    cs=[]; per=TARGET//4
    if not works: return cs
    for _ in range(per):
        a=random.choice(works)
        cs.append({"type":"tac_pham","q":random.choice(T_TP).format(w=a["work"],g=g,bk=BK.get(a["bo"],"")),
                   "g":g,"bo":a["bo"],"work":a["work"]})
    for _ in range(per):
        a=random.choice(works); secs=[x for x in a["secs"] if x in SEC_KW]
        if not secs: continue
        sec=random.choice(secs)
        cs.append({"type":"section","q":random.choice(T_SEC).format(w=a["work"],sec=SEC_KW[sec]),
                   "g":g,"bo":a["bo"],"work":a["work"],"section":sec})
    for _ in range(per):
        a=random.choice(works); vs=[x for x in a["vars"] if x in VAR_KW and x!="standard"]
        if not vs: continue
        v=random.choice(vs)
        cs.append({"type":"variant","q":random.choice(T_VAR).format(w=a["work"],var=VAR_KW[v]),
                   "g":g,"bo":a["bo"],"work":a["work"],"variant":v})
    for _ in range(per):
        a=random.choice(works)
        cs.append({"type":"noi_dung","q":random.choice(T_ND).format(w=a["work"]),
                   "g":g,"bo":a["bo"],"work":a["work"]})
    return cs

def detect_sec(qf):
    for st,kw in SEC_KW.items():
        if fold(kw) in qf: return st
    return None
def detect_var(qf):
    for v,kw in VAR_KW.items():
        if kw and fold(kw) in qf: return v
    return None

def retrieve(case, sess):
    qf=fold(case["q"])
    sec=detect_sec(qf); var=detect_var(qf)
    cy="""MATCH (k:KnowledgeChunk) WHERE k.subject_code='ngu_van' AND coalesce(k.production_ready,false)=true
            AND (k.grade=$g OR toString(k.grade)=toString($g)) AND k.bo_sach=$bo AND k.work_name_norm IS NOT NULL
          WITH k, $qf AS q, k.work_name_norm AS wnf
          WITH k, q, wnf, [w IN split(wnf,' ') WHERE size(w)>=4] AS ww
          WITH k, q, wnf, ww, [w IN ww WHERE q CONTAINS w] AS hits
          WHERE (q CONTAINS wnf AND size(wnf)>=4) OR (size(ww)>=2 AND size(hits)>=2) """
    params={"g":case["g"],"bo":case["bo"],"qf":qf}
    if sec: cy+=" AND k.section_type=$sec "; params["sec"]=sec
    if var: cy+=" AND k.variant=$var "; params["var"]=var
    cy+=""" RETURN k.work_name AS work, k.section_type AS sec, k.variant AS variant, k.grade AS g,
                   (CASE WHEN q CONTAINS wnf THEN 1000 ELSE size(hits) END) AS ms
            ORDER BY ms DESC, size(wnf) DESC LIMIT 1"""
    r=sess.run(cy, **params).data()
    return r[0] if r else None

def score(case,res):
    if not res: return {"hit":False,"grade_ok":True}
    g_ok=str(res["g"])==str(case["g"])
    wmatch=fold(case["work"]) in fold(res.get("work","")) or fold(res.get("work","")) in fold(case["work"])
    hit=wmatch and g_ok
    if case["type"]=="section" and case.get("section"):
        hit=hit and (res.get("sec")==case["section"])
    if case["type"]=="variant" and case.get("variant"):
        hit=hit and (res.get("variant")==case["variant"])
    return {"hit":hit,"grade_ok":g_ok}

print("pull anchors..."); A=pull()
allc=[]
for g in range(6,10):
    cs=gen(g,A[g]); allc+=cs
    print(f"  G{g}: works={len(A[g])} → {len(cs)} cases")
print(f"total: {len(allc)}\nrun...")
res=defaultdict(lambda: defaultdict(lambda:{"n":0,"hit":0,"leak":0}))
with drv.session() as sess:
    for i,c in enumerate(allc):
        r=retrieve(c,sess); sc=score(c,r); cell=res[c["g"]][c["type"]]
        cell["n"]+=1
        if sc["hit"]: cell["hit"]+=1
        if not sc["grade_ok"]: cell["leak"]+=1
        if i%400==0: print(f"  ...{i}/{len(allc)}")
types=["tac_pham","section","variant","noi_dung"]
print("\n=== HIT-RATE grade × type ===")
print("grade | "+" | ".join(f"{t:9}" for t in types)+" | OVERALL")
tot=defaultdict(lambda:{"n":0,"hit":0,"leak":0})
for g in range(6,10):
    row=f"  G{g}  | "; gn=gh=0
    for t in types:
        c=res[g][t]; pct=100*c["hit"]/c["n"] if c["n"] else 0
        row+=f"{pct:5.1f}({c['n']:3})| "; gn+=c["n"]; gh+=c["hit"]
        tot[t]["n"]+=c["n"]; tot[t]["hit"]+=c["hit"]; tot[t]["leak"]+=c["leak"]
    row+=f"{(100*gh/gn if gn else 0):5.1f}%"; print(row)
print("\n=== TOTAL by type ===")
for t in types:
    c=tot[t]; print(f"  {t:9}: {(100*c['hit']/c['n'] if c['n'] else 0):5.1f}% ({c['hit']}/{c['n']}) leak={c['leak']}")
n=sum(c['n'] for c in tot.values()); h=sum(c['hit'] for c in tot.values())
print(f"\n  OVERALL: {100*h/n:.1f}% ({h}/{n})")
json.dump({str(g):{t:dict(res[g][t]) for t in types} for g in range(6,10)},
          open("/tmp/eval_van_results.json","w"), ensure_ascii=False, indent=2)
drv.close()
