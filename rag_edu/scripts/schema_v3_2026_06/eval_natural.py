#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Natural-language eval: Gemma4 sinh query giọng học sinh thật (khẩu ngữ, vòng vo, voice-style),
grounded on real anchors. Run emulated retrieval (fixed T-C/C2 + đ→d). Toán + Văn."""
import re, unicodedata, random, json, requests
from collections import defaultdict
from neo4j import GraphDatabase
drv=GraphDatabase.driver("bolt://localhost:7688",auth=("neo4j","CHANGEME_NEO4J_PASS"))
GEMMA="http://localhost:8080/v1/chat/completions"; KEY="CHANGEME_GEMMA_KEY"
random.seed(2026)
def fold(s):
    s=(s or "").replace("đ","d").replace("Đ","D"); s=unicodedata.normalize("NFD",s)
    return "".join(c for c in s if unicodedata.category(c)!="Mn").lower()

def gemma(prompt):
    b={"model":"gemma-4","messages":[
        {"role":"system","content":"Bạn mô phỏng học sinh Việt Nam nói chuyện VỚI GIA SƯ AI bằng GIỌNG NÓI tự nhiên. Khẩu ngữ, có thể vòng vo, thêm 'ơi/ạ/với', đôi khi nói thiếu hoặc không chuẩn như lời nói thật. KHÔNG trang trọng như văn viết."},
        {"role":"user","content":prompt}],"max_tokens":80,"temperature":1.0}
    try:
        r=requests.post(GEMMA,headers={"Authorization":f"Bearer {KEY}"},json=b,timeout=40)
        return r.json()["choices"][0]["message"]["content"].strip().strip('"').split("\n")[0]
    except Exception as e:
        return f"[err]"

# ---- Toán retrieval (emulated, fixed) ----
def toan_ret(q,g,bo,sess):
    ql=q.lower(); qf=fold(q)
    mb=re.search(r"\bb[àa]i\s*(\d+)",ql); mt=re.search(r"\btrang\s*(\d+)",ql)
    if mb or mt:
        cy="MATCH (k:KnowledgeChunk) WHERE k.subject_code='toan' AND coalesce(k.production_ready,false)=true AND (k.grade=$g OR toString(k.grade)=toString($g)) AND k.bo_sach=$bo "
        p={"g":g,"bo":bo}
        if mb: cy+=" AND (k.lesson_no=$bai OR toLower(k.title) CONTAINS $bc) "; p["bai"]=int(mb.group(1)); p["bc"]=f"bài {mb.group(1)}:"
        if mt: cy+=" AND toLower(k.title) CONTAINS $tr "; p["tr"]=f"trang {mt.group(1)}"
        cy+=" RETURN k.title AS title, k.lesson_no AS ln, k.trang_no AS trang ORDER BY CASE WHEN k.content_class='vietjack_lesson' THEN 0 ELSE 1 END LIMIT 1"
        r=sess.run(cy,**p).data()
        if r: return ("struct",r[0])
    cy="""MATCH (k:KnowledgeChunk)-[:COVERS]->(c:Concept) WHERE coalesce(k.production_ready,false)=true AND (k.grade=$g OR toString(k.grade)=toString($g)) AND k.bo_sach=$bo AND k.subject_code='toan' AND c.name_norm IS NOT NULL AND size(c.name_norm)>=3
      WITH k,c,$qf AS q WITH k,c,q,[w IN split(c.name_norm,' ') WHERE size(w)>=4] AS cw WITH k,c,q,cw,[w IN cw WHERE q CONTAINS w] AS h
      WHERE q CONTAINS c.name_norm OR (size(cw)>=2 AND size(h)>=2)
      RETURN c.name AS concept,(CASE WHEN q CONTAINS c.name_norm THEN 1000 ELSE size(h) END) AS ms ORDER BY ms DESC, size(c.name_norm) DESC LIMIT 1"""
    r=sess.run(cy,g=g,bo=bo,qf=qf).data()
    return ("concept",r[0]) if r else ("miss",None)

def van_ret(q,g,bo,sess):
    qf=fold(q)
    RE=["doc ca bai","doc thuoc","ngam","hoc thuoc","doc dien cam","doc cho"]
    if any(k in qf for k in RE):
        r=sess.run("MATCH (lt:LiteratureText)-[:VERBATIM_OF]->(w:LiteraryWork) WHERE w.name_norm IS NOT NULL AND size(w.name_norm)>=4 AND $q CONTAINS w.name_norm RETURN w.name AS work,'recite' AS t LIMIT 1",q=qf).data()
        if r: return ("recite",r[0])
    cy="""MATCH (k:KnowledgeChunk) WHERE k.subject_code='ngu_van' AND coalesce(k.production_ready,false)=true AND (k.grade=$g OR toString(k.grade)=toString($g)) AND k.bo_sach=$bo AND k.work_name_norm IS NOT NULL
      WITH k,$qf AS q,k.work_name_norm AS wnf WITH k,q,wnf,[w IN split(wnf,' ') WHERE size(w)>=4] AS ww WITH k,q,wnf,ww,[w IN ww WHERE q CONTAINS w] AS h
      WHERE (q CONTAINS wnf AND size(wnf)>=4) OR (size(ww)>=2 AND size(h)>=2)
      RETURN k.work_name AS work,(CASE WHEN q CONTAINS wnf THEN 1000 ELSE size(h) END) AS ms ORDER BY ms DESC, size(wnf) DESC LIMIT 1"""
    r=sess.run(cy,g=g,bo=bo,qf=qf).data()
    return ("work",r[0]) if r else ("miss",None)

# ---- pull anchors ----
with drv.session() as s:
    toan_les=[dict(r) for r in s.run("MATCH (k:KnowledgeChunk) WHERE k.subject_code='toan' AND k.production_ready=true AND k.content_class='vietjack_lesson' AND k.lesson_no IS NOT NULL AND k.title=~'.*Bài \\\\d+:.*' WITH k,split(k.title,': ')[-1] AS c WHERE size(c)>3 AND size(c)<55 RETURN toInteger(k.grade) AS g,k.bo_sach AS bo,k.lesson_no AS ln,c AS concept ORDER BY rand() LIMIT 30")]
    toan_pg=[dict(r) for r in s.run("MATCH (k:KnowledgeChunk) WHERE k.subject_code='toan' AND k.production_ready=true AND k.trang_no IS NOT NULL RETURN toInteger(k.grade) AS g,k.bo_sach AS bo,k.trang_no AS trang ORDER BY rand() LIMIT 15")]
    van_w=[dict(r) for r in s.run("MATCH (k:KnowledgeChunk) WHERE k.subject_code='ngu_van' AND k.production_ready=true AND k.work_name IS NOT NULL RETURN toInteger(k.grade) AS g,k.bo_sach AS bo,k.work_name AS work ORDER BY rand() LIMIT 30")]

cases=[]
for a in toan_les[:15]:
    cases.append(("toan","bài",a,gemma(f"Em học Toán lớp {a['g']}. Em muốn nhờ gia sư giảng Bài {a['ln']} (chủ đề '{a['concept']}'). Nói 1 câu tự nhiên, có nhắc số bài.")))
for a in toan_les[15:30]:
    cases.append(("toan","concept",a,gemma(f"Em học Toán lớp {a['g']}. Em chưa hiểu '{a['concept']}'. Hỏi gia sư 1 câu tự nhiên kiểu khẩu ngữ (KHÔNG cần nói 'bài mấy').")))
for a in toan_pg:
    cases.append(("toan","trang",a,gemma(f"Em học Toán lớp {a['g']} sách {a['bo']}, đang mở trang {a['trang']}. Nhờ gia sư giải bài trang đó — nói 1 câu tự nhiên.")))
for a in van_w[:15]:
    cases.append(("van","work",a,gemma(f"Em học Ngữ văn lớp {a['g']}. Nhờ gia sư giảng/soạn tác phẩm '{a['work']}'. Nói 1 câu tự nhiên khẩu ngữ.")))
for a in van_w[15:25]:
    cases.append(("van","content",a,gemma(f"Em học Ngữ văn lớp {a['g']}. Hỏi gia sư về nội dung/cảm nghĩ/phân tích tác phẩm '{a['work']}' — 1 câu tự nhiên, KHÔNG nói chữ 'soạn bài'.")))
for a in van_w[25:30]:
    cases.append(("van","recite",a,gemma(f"Em học Ngữ văn lớp {a['g']}. Muốn nghe ĐỌC nguyên văn/đọc thuộc tác phẩm '{a['work']}'. Nói 1 câu tự nhiên.")))

res=defaultdict(lambda:{"n":0,"hit":0})
samples=[]
with drv.session() as sess:
    for subj,typ,a,q in cases:
        if q=="[err]": continue
        if subj=="toan":
            tier,r=toan_ret(q,a["g"],a["bo"],sess)
            if typ=="trang": hit = r and str(r.get("trang"))==str(a["trang"])
            elif typ=="bài": hit = r and (r.get("ln")==a["ln"] or fold(a["concept"]) in fold(r.get("title","")))
            else: hit = r and fold(a["concept"]) in fold(r.get("concept","") or "")
        else:
            tier,r=van_ret(q,a["g"],a["bo"],sess)
            hit = r and (fold(a["work"]) in fold(r.get("work","")) or fold(r.get("work","")) in fold(a["work"]))
        res[(subj,typ)]["n"]+=1; res[(subj,typ)]["hit"]+=1 if hit else 0
        if len(samples)<24: samples.append((subj,typ,a.get("g"),q[:75],tier,"✓" if hit else "✗"))

print("=== SAMPLE natural queries (Gemma4) ===")
for s_ in samples: print(f"  [{s_[0]}/{s_[1]}] G{s_[2]} {s_[5]} tier={s_[4]}\n      {s_[3]}")
print("\n=== HIT by (subject,type) on NATURAL language ===")
for k,v in sorted(res.items()):
    print(f"  {k[0]:4}/{k[1]:8}: {100*v['hit']/v['n']:5.1f}% ({v['hit']}/{v['n']})")
tn=sum(v['n'] for v in res.values()); th=sum(v['hit'] for v in res.values())
print(f"\n  OVERALL natural: {100*th/tn:.1f}% ({th}/{tn})")
drv.close()
