#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Comprehensive Toán eval G1-9, ~500 queries/grade, 4 types (trang/bài/kiến thức/cách giải).
Emulates the PATCHED retrieval (query_structured_exact + query_concept_exact T-C/C2) directly
via Cypher against Neo4j — NO canary HTTP needed. Reports grade×type hit matrix."""
import re, unicodedata, random, json
from collections import defaultdict
from neo4j import GraphDatabase

drv = GraphDatabase.driver("bolt://localhost:7688", auth=("neo4j","CHANGEME_NEO4J_PASS"))
random.seed(42)
TARGET_PER_GRADE = 500

def fold(s):
    s = (s or '').replace('đ','d').replace('Đ','D')
    s = unicodedata.normalize('NFD', s)
    return ''.join(c for c in s if unicodedata.category(c) != 'Mn').lower()

# ---------- pull anchors per grade ----------
def pull():
    A = defaultdict(lambda: {"lessons":[], "pages":[], "concepts":[]})
    with drv.session() as s:
        for r in s.run("""
            MATCH (k:KnowledgeChunk) WHERE k.subject_code='toan' AND k.production_ready=true
              AND k.content_class='vietjack_lesson' AND k.lesson_no IS NOT NULL AND k.title=~'.*Bài \\\\d+:.*'
            WITH k, split(k.title,': ')[-1] AS concept
            RETURN toInteger(k.grade) AS g, k.bo_sach AS bo, k.lesson_no AS ln, concept AS concept, k.uid AS uid
        """):
            d=dict(r)
            if 3<len(d["concept"])<60: A[d["g"]]["lessons"].append(d)
        for r in s.run("""
            MATCH (k:KnowledgeChunk) WHERE k.subject_code='toan' AND k.production_ready=true AND k.trang_no IS NOT NULL
            RETURN toInteger(k.grade) AS g, k.bo_sach AS bo, k.trang_no AS trang, k.uid AS uid
        """):
            A[dict(r)["g"]]["pages"].append(dict(r))
        for r in s.run("""
            MATCH (c:Concept {subject:'toan',level:'fine'})<-[:COVERS]-(k:KnowledgeChunk {production_ready:true})
            RETURN DISTINCT toInteger(k.grade) AS g, k.bo_sach AS bo, c.name AS concept, c.name_norm AS nf
        """):
            A[dict(r)["g"]]["concepts"].append(dict(r))
    return A

# ---------- query templates ----------
T_BAI = ["bài {n} toán lớp {g}", "cô ơi giảng bài {n} lớp {g} với", "em đang làm bài {n} toán {g}",
         "bài {n} {bk} làm sao ạ", "giảng giúp em bài {n} {cc}", "bài {n} {cc} em chưa hiểu"]
T_TRANG = ["giải trang {p} toán lớp {g}", "trang {p} bài tập khó quá cô ơi", "cô ơi trang {p} sách {bk}",
           "giải giúp em bài ở trang {p} toán {g}", "trang {p} làm thế nào ạ"]
T_KT = ["{cc} là gì ạ", "cô ơi {cc} là sao", "em chưa hiểu {cc}", "giải thích {cc} cho em", "{cc} nghĩa là gì"]
T_CG = ["cách giải {cc} thế nào", "làm {cc} thế nào ạ", "cách làm dạng {cc}", "{cc} giải sao ạ", "phương pháp làm {cc}"]
BK = {"KNTT":"kết nối tri thức","CTST":"chân trời sáng tạo","CD":"cánh diều"}

def gen_for_grade(g, anc):
    cases=[]
    L,P,C = anc["lessons"], anc["pages"], anc["concepts"]
    # split target across 4 types
    per = TARGET_PER_GRADE//4
    # theo_bai
    if L:
        for i in range(per):
            a=random.choice(L); t=random.choice(T_BAI)
            q=t.format(n=a["ln"], g=g, bk=BK.get(a["bo"],""), cc=a["concept"])
            cases.append({"type":"theo_bai","q":q,"g":g,"bo":a["bo"],"ln":a["ln"],"concept":a["concept"]})
    # theo_trang
    if P:
        for i in range(per):
            a=random.choice(P); t=random.choice(T_TRANG)
            q=t.format(p=a["trang"], g=g, bk=BK.get(a["bo"],""))
            cases.append({"type":"theo_trang","q":q,"g":g,"bo":a["bo"],"trang":a["trang"]})
    # kien_thuc + cach_giai
    if C:
        for i in range(per):
            a=random.choice(C); q=random.choice(T_KT).format(cc=a["concept"])
            cases.append({"type":"kien_thuc","q":q,"g":g,"bo":a["bo"],"concept":a["concept"],"nf":a["nf"]})
        for i in range(per):
            a=random.choice(C); q=random.choice(T_CG).format(cc=a["concept"])
            cases.append({"type":"cach_giai","q":q,"g":g,"bo":a["bo"],"concept":a["concept"],"nf":a["nf"]})
    return cases

# ---------- emulated retrieval (mirrors patched canary) ----------
def parse(q, g, bo):
    ql=q.lower()
    m_bai=re.search(r"\bb[àa]i\s*(\d+)", ql); m_tr=re.search(r"\btrang\s*(\d+)", ql)
    return {"lop":g,"bo":bo,"bai":int(m_bai.group(1)) if m_bai else None,
            "trang":int(m_tr.group(1)) if m_tr else None,"qf":fold(q)}

def retrieve(p, sess):
    # Tier A structured
    if p["bai"] or p["trang"]:
        cy="""MATCH (k:KnowledgeChunk) WHERE k.subject_code='toan' AND coalesce(k.production_ready,false)=true
              AND (k.grade=$g OR toString(k.grade)=toString($g)) AND k.bo_sach=$bo """
        if p["bai"]:
            cy+=" AND (k.lesson_no=$bai OR toLower(k.title) CONTAINS $bc) "
        if p["trang"]:
            cy+=" AND toLower(k.title) CONTAINS $trtext "
        cy+=""" RETURN k.grade AS g, k.bo_sach AS bo, k.lesson_no AS ln, k.title AS title, k.trang_no AS trang
                ORDER BY CASE WHEN k.content_class='vietjack_lesson' THEN 0 ELSE 1 END,
                         CASE WHEN k.lesson_no=$bai THEN 0 ELSE 1 END LIMIT 1"""
        r=sess.run(cy, g=p["lop"], bo=p["bo"], bai=p["bai"], bc=f"bài {p['bai']}:" if p['bai'] else "",
                   trtext=f"trang {p['trang']}" if p["trang"] else "").data()
        if r: return ("A_structured", r[0])
    # Tier A concept (word-overlap, T-C2)
    cy="""MATCH (k:KnowledgeChunk)-[:COVERS]->(c:Concept)
          WHERE coalesce(k.production_ready,false)=true AND (k.grade=$g OR toString(k.grade)=toString($g))
            AND k.bo_sach=$bo AND k.subject_code='toan' AND c.name_norm IS NOT NULL AND size(c.name_norm)>=3
          WITH k,c,$qf AS q
          WITH k,c,q,[w IN split(c.name_norm,' ') WHERE size(w)>=4] AS cw
          WITH k,c,q,cw,[w IN cw WHERE q CONTAINS w] AS hits
          WHERE q CONTAINS c.name_norm OR (size(cw)>=2 AND size(hits)>=2)
          RETURN k.grade AS g, k.bo_sach AS bo, k.lesson_no AS ln, k.title AS title, c.name AS concept,
                 (CASE WHEN q CONTAINS c.name_norm THEN 1000 ELSE size(hits) END) AS ms
          ORDER BY ms DESC, CASE WHEN k.content_class='vietjack_lesson' THEN 0 ELSE 1 END LIMIT 1"""
    r=sess.run(cy, g=p["lop"], bo=p["bo"], qf=p["qf"]).data()
    if r: return ("A_concept", r[0])
    return ("miss", None)

def score(case, tier, res):
    if res is None: return {"hit":False,"tier":tier,"grade_ok":True}
    grade_ok = str(res["g"])==str(case["g"])
    hit=False
    if case["type"]=="theo_bai":
        hit = (res.get("ln")==case["ln"]) or (fold(case["concept"]) in fold(res.get("title","")))
    elif case["type"]=="theo_trang":
        hit = str(res.get("trang"))==str(case["trang"])
    else:
        hit = fold(case["concept"]) in fold(res.get("title","")) or fold(case.get("concept","")) in fold(res.get("concept","") or "")
    return {"hit":hit and grade_ok,"tier":tier,"grade_ok":grade_ok}

# ---------- run ----------
print("pulling anchors...")
A=pull()
allcases=[]
for g in range(1,10):
    cs=gen_for_grade(g, A[g]); allcases+=cs
    print(f"  G{g}: lessons={len(A[g]['lessons'])} pages={len(A[g]['pages'])} concepts={len(A[g]['concepts'])} → {len(cs)} cases")
print(f"total cases: {len(allcases)}\nrunning emulated retrieval...")

res=defaultdict(lambda: defaultdict(lambda:{"n":0,"hit":0,"leak":0}))
with drv.session() as sess:
    for i,c in enumerate(allcases):
        p=parse(c["q"], c["g"], c["bo"])
        tier,r=retrieve(p, sess)
        sc=score(c,tier,r)
        cell=res[c["g"]][c["type"]]
        cell["n"]+=1
        if sc["hit"]: cell["hit"]+=1
        if not sc["grade_ok"]: cell["leak"]+=1
        if i%500==0: print(f"  ...{i}/{len(allcases)}")

print("\n=== HIT-RATE by grade × type (hit% | n) ===")
types=["theo_bai","theo_trang","kien_thuc","cach_giai"]
print("grade | " + " | ".join(f"{t:10}" for t in types) + " | OVERALL")
tot=defaultdict(lambda:{"n":0,"hit":0,"leak":0})
for g in range(1,10):
    row=f"  G{g}  | "
    gn=gh=0
    for t in types:
        c=res[g][t]; pct=(100*c["hit"]/c["n"]) if c["n"] else 0
        row+=f"{pct:5.1f}({c['n']:3}) | "; gn+=c["n"]; gh+=c["hit"]
        tot[t]["n"]+=c["n"]; tot[t]["hit"]+=c["hit"]; tot[t]["leak"]+=c["leak"]
    row+=f"{(100*gh/gn if gn else 0):5.1f}%"
    print(row)
print("\n=== TOTAL by type ===")
for t in types:
    c=tot[t]; print(f"  {t:11}: {100*c['hit']/c['n']:5.1f}% hit ({c['hit']}/{c['n']}), cross-grade leak={c['leak']}")
gtot_n=sum(c['n'] for c in tot.values()); gtot_h=sum(c['hit'] for c in tot.values())
print(f"\n  OVERALL: {100*gtot_h/gtot_n:.1f}% ({gtot_h}/{gtot_n})")
with open("/tmp/eval_toan_full_results.json","w") as f:
    json.dump({str(g):{t:dict(res[g][t]) for t in types} for g in range(1,10)}, f, ensure_ascii=False, indent=2)
print("saved /tmp/eval_toan_full_results.json")
drv.close()
