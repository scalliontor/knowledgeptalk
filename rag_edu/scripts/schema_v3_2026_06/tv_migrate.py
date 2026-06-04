#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tiếng Việt G1-5 migration to schema v3 (hybrid Toán+Văn).
Extract lesson_no + trang_no + content_class + reading-text concept (gated, đ→d norm) + COVERS."""
import re, unicodedata
from collections import Counter
from neo4j import GraphDatabase
drv=GraphDatabase.driver("bolt://localhost:7688",auth=("neo4j","CHANGEME_NEO4J_PASS"))
ACTOR="TV_MIGRATE_2026_06_04"
def fold(s):
    s=(s or "").replace("đ","d").replace("Đ","D").replace("–","-").replace("—","-")
    s=unicodedata.normalize("NFD",s)
    return "".join(c for c in s if unicodedata.category(c)!="Mn").lower()
def slug(s): return re.sub(r'[^a-z0-9]+','_',fold(s)).strip('_')[:60]

# skill prefixes to strip from the bài-name to get the reading text / topic
SKILL_PREFIX=re.compile(r'^(nghe\s*-\s*viet|nghe\s*-\s*ke|nghe\s*-\s*noi|luyen tu va cau|tap doc|chinh ta|tap viet|tap lam van|ke chuyen|noi va nghe|noi nghe|doc|viet|on tap|danh gia|luyen tap)\s*:?\s*')
# whole-title is a non-content activity -> skip concept
SKILL_WHOLE=re.compile(r'(de kiem tra|de thi|on tap giua|on tap cuoi|on tap hoc ki|danh gia cuoi|danh gia giua|phieu|tu danh gia|muc luc|loi noi dau)')

def extract(title):
    t=title
    m_bai=re.search(r'B[àa]i\s+(\d+)\s*:', t)
    ln=int(m_bai.group(1)) if m_bai else None
    m_tr=re.search(r'trang\s+(\d+)', t)
    tr=int(m_tr.group(1)) if m_tr else None
    # content_class
    tf=fold(t)
    if 'vbt' in tf or 'vo bai tap' in tf: cc='tv_vbt'
    elif SKILL_WHOLE.search(tf): cc='tv_assessment'
    else: cc='tv_lesson'
    # concept = reading-text/topic name: strip leading "Giải", "Bài N:", skill-prefix; cut at " trang"/" SGK"/" VBT"/" |"
    name=t
    name=re.sub(r'^Gi[ảa]i\s+','',name)
    name=re.sub(r'^B[àa]i\s+\d+\s*:\s*','',name)
    name=re.split(r'\s+(?:trang\s+\d+|SGK|VBT|\|)', name)[0].strip()
    nf_pref=SKILL_PREFIX.sub('', fold(name))
    # if after stripping skill prefix nothing meaningful, or whole is skill -> no concept
    GENERIC={'luyen tap','on tap','doc mo rong','em doc sach bao','doc','viet','noi va nghe',
             'tu doc sach bao','goc sang tao','van nghe','tu danh gia','danh gia','cung co'}
    concept=None
    if cc=='tv_lesson' and not SKILL_WHOLE.search(fold(name)) and len(name)>3 and len(name)<70:
        parts=name.split(': ')
        disp=parts[-1].strip() if len(parts)>1 else name
        df=fold(disp)
        if (len(disp)>3 and not SKILL_WHOLE.search(df) and df not in GENERIC
            and not re.match(r'^tiet \d+$',df) and not re.match(r'^bai \d+$',df)):
            concept=disp
    return ln,tr,cc,concept

with drv.session() as s:
    rows=list(s.run("MATCH (k:KnowledgeChunk) WHERE k.subject_code='tieng_viet' AND k.production_ready=true RETURN k.uid AS uid, k.title AS title"))
print(f"TV prod chunks: {len(rows)}")
reg=Counter(); cmap={}; nln=ntr=ncc=0
with drv.session() as s:
    for r in rows:
        ln,tr,cc,concept=extract(r["title"])
        sets=["k.content_class=$cc","k.tv_actor=$a"]; p={"uid":r["uid"],"cc":cc,"a":ACTOR}
        if ln is not None: sets.append("k.lesson_no=coalesce(k.lesson_no,$ln)"); p["ln"]=ln; nln+=1
        if tr is not None: sets.append("k.trang_no=coalesce(k.trang_no,$tr)"); p["tr"]=tr; ntr+=1
        if concept: sets.append("k.concept_name=$cn"); p["cn"]=concept; reg[concept]+=1; cmap[r["uid"]]=concept
        s.run(f"MATCH (k:KnowledgeChunk {{uid:$uid}}) SET {','.join(sets)}", **p); ncc+=1
print(f"set content_class={ncc} lesson_no~{nln} trang_no~{ntr} | distinct concepts={len(reg)}")
print("Top 12 reading-texts:")
for w,c in reg.most_common(12): print(f"  {c:2}  {w}")
# concept nodes + COVERS
with drv.session() as s:
    for concept,_ in reg.items():
        cid=f"tieng_viet.{slug(concept)}"
        s.run("""MERGE (c:Concept {concept_id:$cid}) SET c.name=$n,c.name_norm=$nf,c.subject='tieng_viet',c.level='fine',c.source='tv_title',c.created_actor=$a""",
              cid=cid,n=concept,nf=fold(concept),a=ACTOR)
    edges=0
    for uid,concept in cmap.items():
        cid=f"tieng_viet.{slug(concept)}"
        s.run("MATCH (k:KnowledgeChunk {uid:$uid}),(c:Concept {concept_id:$cid}) MERGE (k)-[:COVERS]->(c) SET k.concept_id_fine=$cid",uid=uid,cid=cid)
        edges+=1
    print(f"concepts created={len(reg)} COVERS={edges}")
    v=s.run("""MATCH (k:KnowledgeChunk) WHERE k.subject_code='tieng_viet' AND k.production_ready=true
        RETURN count(*) AS t, sum(CASE WHEN k.lesson_no IS NOT NULL THEN 1 ELSE 0 END) AS ln,
          sum(CASE WHEN k.trang_no IS NOT NULL THEN 1 ELSE 0 END) AS tr,
          sum(CASE WHEN k.concept_name IS NOT NULL THEN 1 ELSE 0 END) AS cn""").single()
    print(f"VERIFY: total={v['t']} lesson_no={v['ln']} trang_no={v['tr']} concept={v['cn']}")
drv.close()
