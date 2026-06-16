#!/usr/bin/env python3
"""GENERIC BOOK BUILDER — dựng companion Lesson Card cho 1 quyển BẤT KỲ.
Usage: build_book_generic.py <subject> <grade> <book> [tap|auto]
Tự: (1) suy manifest từ DB (Bài N + work_name + tap-signal + trang), (2) Gemma synth theory+practice theo LOẠI MÔN,
(3) ingest :Lesson + theory(BGE) + practice_json + trang range. Actor = <SUBJECT>_PILOT_2026_06. Idempotent (MERGE).
"""
import sys, json, re, urllib.request, unicodedata, os
os.environ['HF_HOME']="/home/namnx/.cache/huggingface"
from neo4j import GraphDatabase
from sentence_transformers import SentenceTransformer

SUBJECT=sys.argv[1]; GRADE=int(sys.argv[2]); BOOK=sys.argv[3]
TAP_ARG=sys.argv[4] if len(sys.argv)>4 else "auto"
NEO=GraphDatabase.driver("bolt://localhost:7688",auth=("neo4j",__import__("os").environ.get("EDU_NEO4J_PW","")))
GEMMA_URL="http://localhost:8080/v1/chat/completions"; GKEY=__import__("os").environ.get("GEMMA_KEY","")
ACTOR=f"{SUBJECT.upper()}_PILOT_2026_06"

FAMILY={"ngu_van":"literature","tieng_viet":"literature","toan":"math",
 "khtn":"science","vat_li":"science","hoa_hoc":"science","sinh_hoc":"science",
 "lich_su":"social","dia_li":"social","lich_su_dia_li":"social","tnxh":"social",
 "gdcd":"civic","cong_nghe":"science","tieng_anh":"language"}
fam=FAMILY.get(SUBJECT,"science")

# subject-aware synth schema (fields + prompt)
SCHEMAS={
 "math":('{"dinh_nghia":"<khái niệm cốt lõi 1-3 câu>","kien_thuc_chinh":["..3-4.."],"cong_thuc":["..hoặc[]"],'
   '"vi_du":[{"de":"<có số cụ thể>","giai":"<ra kết quả>"}],"luu_y":"<1 câu>",'
   '"cau_hoi_dan_dat":["..3.."],"practice":[{"cau":"Câu 1","cau_hoi":"..","goi_y":"..","dap_an":".."},{"cau":"Câu 2","cau_hoi":"..","goi_y":"..","dap_an":".."},{"cau":"Câu 3","cau_hoi":"..","goi_y":"..","dap_an":".."}]}'),
 "science":('{"dinh_nghia":"<khái niệm/hiện tượng cốt lõi>","kien_thuc_chinh":["..3-4.."],"cong_thuc":["..hoặc[]"],'
   '"vi_du":[{"de":"<ví dụ/hiện tượng thực tế>","giai":"<giải thích>"}],"luu_y":"<1 câu>",'
   '"cau_hoi_dan_dat":["..3.."],"practice":[{"cau":"Câu 1","cau_hoi":"..","goi_y":"..","dap_an":".."},{"cau":"Câu 2","cau_hoi":"..","goi_y":"..","dap_an":".."},{"cau":"Câu 3","cau_hoi":"..","goi_y":"..","dap_an":".."}]}'),
 "social":('{"dinh_nghia":"<chủ đề/sự kiện chính của bài, 1-2 câu>","kien_thuc_chinh":["..bối cảnh/nguyên nhân/diễn biến/đặc điểm 4.."],"cong_thuc":[],'
   '"vi_du":[{"de":"<mốc/dẫn chứng cụ thể>","giai":"<ý nghĩa>"}],"luu_y":"<điều dễ nhầm, 1 câu>",'
   '"cau_hoi_dan_dat":["..3.."],"practice":[{"cau":"Câu 1","cau_hoi":"..","goi_y":"..","dap_an":".."},{"cau":"Câu 2","cau_hoi":"..","goi_y":"..","dap_an":".."},{"cau":"Câu 3","cau_hoi":"..","goi_y":"..","dap_an":".."}]}'),
 "civic":('{"dinh_nghia":"<khái niệm đạo đức/pháp luật của bài>","kien_thuc_chinh":["..biểu hiện/ý nghĩa/vai trò 3-4.."],"cong_thuc":[],'
   '"vi_du":[{"de":"<tình huống thực tế>","giai":"<cách ứng xử/bài học>"}],"luu_y":"<1 câu>",'
   '"cau_hoi_dan_dat":["..3.."],"practice":[{"cau":"Câu 1","cau_hoi":"..","goi_y":"..","dap_an":".."},{"cau":"Câu 2","cau_hoi":"..","goi_y":"..","dap_an":".."},{"cau":"Câu 3","cau_hoi":"..","goi_y":"..","dap_an":".."}]}'),
 "literature":('{"tac_gia":"<1-2 câu, để trống nếu bài kỹ năng>","hoan_canh":"<1 câu hoặc trống>","the_loai":"<thể loại>",'
   '"bo_cuc":["..phần.."],"noi_dung_chinh":"<3-4 câu>","gia_tri_noi_dung":"<2 câu>","gia_tri_nghe_thuat":"<2 câu>",'
   '"cau_hoi_dan_dat":["..3.."],"practice":[{"cau":"Câu 1","cau_hoi":"..","goi_y":"..","dap_an":".."},{"cau":"Câu 2","cau_hoi":"..","goi_y":"..","dap_an":".."},{"cau":"Câu 3","cau_hoi":"..","goi_y":"..","dap_an":".."}]}'),
}
SCHEMAS["language"]=SCHEMAS["literature"]
ROLE={"math":"giáo viên Toán","science":"giáo viên Khoa học tự nhiên","social":"giáo viên Lịch sử & Địa lí",
 "civic":"giáo viên GDCD","literature":"giáo viên Ngữ văn","language":"giáo viên Tiếng Việt"}[fam]

def gemma(sysp,usr,mx=2200):
    body=json.dumps({"model":"gemma-4","messages":[{"role":"system","content":sysp},{"role":"user","content":usr}],"temperature":0.1,"max_tokens":mx}).encode()
    r=urllib.request.Request(GEMMA_URL,data=body,headers={"Authorization":f"Bearer {GKEY}","Content-Type":"application/json"})
    return json.loads(urllib.request.urlopen(r,timeout=120).read())["choices"][0]["message"]["content"]
def fold(s):
    s=(s or "").replace("đ","d").replace("Đ","D"); s=unicodedata.normalize("NFD",s)
    return "".join(c for c in s if unicodedata.category(c)!="Mn").lower()
def wslug(s): return re.sub(r"-+","-",re.sub(r"[^a-z0-9]+","-",fold(s))).strip("-")
def sanitize(t):
    t=t or ""; t=re.sub(r"Toán - Văn - Anh[^\n]*","",t)
    t=re.sub(r"\(Giáo viên VietJack\)|Xem lời giải|Xem chi tiết|Bài giảng:.*|Video Giải[^\n]*|Giải bài nhanh với AI Hay","",t)
    return re.sub(r"\n{3,}","\n\n",t).strip()

SKIP=re.compile(r"hoạt động (thực hành|trải nghiệm)|^ôn tập|kiểm tra|đề thi|trắc nghiệm",re.I)
# ── 1. auto-manifest ──
with NEO.session() as s:
    rows=s.run("""MATCH (k:KnowledgeChunk {subject_code:$s,grade:$g,bo_sach:$b})
        WHERE k.title =~ '.*[Bb]ài [0-9]+.*'
        WITH k.title AS title, collect(k.text) AS texts, sum(CASE WHEN k.text CONTAINS 'Tập 2' THEN 1 ELSE 0 END) AS t2,
             sum(CASE WHEN k.text CONTAINS 'Tập 1' THEN 1 ELSE 0 END) AS t1
        RETURN title, texts[0] AS text, t1, t2""", s=SUBJECT,g=GRADE,b=BOOK).data()
manifest=[]
for r in rows:
    t=r["title"]
    if SKIP.search(t): continue
    m=re.search(r"[Bb]ài\s+(\d+)\s*:?\s*(.+)$", t)
    if not m: continue
    ln=int(m.group(1)); work=re.sub(r"\s*-\s*(Toán|Ngữ văn|Khoa học|Lịch [Ss]ử|Địa|GDCD)[^,]*$","",m.group(2)).strip()
    work=re.split(r"\s+(Toán|Ngữ văn|Khoa học tự nhiên|Lịch Sử|Địa Lí)\s+\d", work)[0].strip()
    if len(work)<3: continue
    tap = 2 if r["t2"]>r["t1"] else (1 if r["t1"]>0 else None)
    if TAP_ARG!="auto" and tap is not None and tap!=int(TAP_ARG): continue
    src=sanitize(r["text"] or "")
    trs=sorted(set(int(x) for x in re.findall(r"trang\s*(\d+)",src) if 1<=int(x)<=400))
    manifest.append({"work":work,"ln":ln,"tap":tap,"trang_from":(trs[0] if trs else None),"title":t,"src":src})
# dedup by (work) keep first
seen=set(); manifest=[m for m in manifest if not (m["work"] in seen or seen.add(m["work"]))]
print(f"[{SUBJECT} {GRADE} {BOOK}] manifest = {len(manifest)} bài (family={fam})", flush=True)
if not manifest: print("NO LESSONS — abort"); sys.exit(0)

# ── 2. synth ──
SYS=(f"Bạn là {ROLE} lớp {GRADE} (GDPT 2018) soạn THẺ KIẾN THỨC để chatbot ĐỒNG HÀNH cùng học sinh. "
 "Dựa trên TÊN BÀI + nội dung SGK kèm theo, soạn NGẮN GỌN, CHÍNH XÁC, KHÔNG bịa. Chỉ trả JSON đúng định dạng, tiếng Việt:\n"+SCHEMAS[fam])
for c in manifest:
    usr=f"TÊN BÀI: {c['work']}\nMÔN: {SUBJECT} lớp {GRADE}\n\nNỘI DUNG SGK (trích):\n{c['src'][:6000]}"
    try:
        raw=gemma(SYS,usr).replace("```json","").replace("```","").strip()
        m=re.search(r"\{.*\}",raw,re.S); c.update(json.loads(m.group(0) if m else raw)); c["_ok"]=True
        print(f"  OK B{c['ln']} {c['work'][:40]:42} tap={c['tap']} trang={c['trang_from']}", flush=True)
    except Exception as e:
        c["_ok"]=False; print(f"  ERR B{c['ln']} {c['work'][:40]} -> {e}", flush=True)
# trang_to = next bài by trang_from (within tap)
for tp in set(c["tap"] for c in manifest):
    grp=sorted([c for c in manifest if c["tap"]==tp and c.get("trang_from")],key=lambda x:x["trang_from"])
    for i,c in enumerate(grp): c["trang_to"]=(grp[i+1]["trang_from"]-1) if i+1<len(grp) else c["trang_from"]+4

# ── 3. ingest ──
def card_text(c):
    if fam in ("literature","language"):
        L=[f"Tác phẩm: {c['work']}"]
        for k,lbl in [("tac_gia","Tác giả"),("hoan_canh","Hoàn cảnh"),("the_loai","Thể loại"),("noi_dung_chinh","Nội dung chính"),("gia_tri_noi_dung","Giá trị nội dung"),("gia_tri_nghe_thuat","Giá trị nghệ thuật")]:
            if c.get(k): L.append(f"{lbl}: {c[k]}")
        if c.get("bo_cuc"): L.append("Bố cục:\n- "+"\n- ".join(c["bo_cuc"]))
        return "\n".join(L)
    L=[f"Bài: {c['work']} ({SUBJECT} lớp {GRADE} {BOOK})"]
    if c.get("dinh_nghia"): L.append(f"Khái niệm: {c['dinh_nghia']}")
    if c.get("kien_thuc_chinh"): L.append("Kiến thức chính:\n- "+"\n- ".join(c["kien_thuc_chinh"]))
    if c.get("cong_thuc"): L.append("Công thức / Quy tắc:\n- "+"\n- ".join(c["cong_thuc"]))
    if c.get("vi_du"): L.append("Ví dụ:\n"+"\n".join(f"- {e.get('de','')} → {e.get('giai','')}" for e in c["vi_du"]))
    if c.get("luu_y"): L.append(f"Lưu ý: {c['luu_y']}")
    return "\n".join(L)

print("[ingest] load BGE...", flush=True); bge=SentenceTransformer("BAAI/bge-m3"); print("[ingest] BGE ok", flush=True)
st={"lesson":0,"skip":0}
with NEO.session() as s:
    for c in manifest:
        if not c.get("_ok"): st["skip"]+=1; continue
        w=c["work"]; sl=wslug(w); wn=fold(w); tp=c["tap"]; tf=c.get("trang_from"); tt=c.get("trang_to")
        text=card_text(c)
        if len(text)<40: st["skip"]+=1; continue
        emb=bge.encode([text],normalize_embeddings=True)[0].tolist()
        uid=f"theory_{SUBJECT}_{GRADE}_{BOOK}_{tp}_{sl}"
        gq=json.dumps(c.get("cau_hoi_dan_dat",[]),ensure_ascii=False); pj=json.dumps(c.get("practice",[]),ensure_ascii=False)
        s.run("""MERGE (k:KnowledgeChunk {uid:$uid})
          SET k.text=$text,k.title=$title,k.subject_code=$subj,k.grade=$g,k.bo_sach=$b,k.tap_no=$tp,
              k.work_name=$w,k.work_name_norm=$wn,k.content_type='theory',k.content_class='theory_card',
              k.section_type='ly_thuyet',k.trang_no=$tf,k.production_ready=true,k.source='gemma_synth',
              k.ingest_actor=$actor,k.embedding=$emb,k.embedding_model='bge-m3',k.guiding_questions=$gq""",
          uid=uid,text=text,title=f"Lý thuyết: {w} ({SUBJECT} {GRADE} {BOOK})",subj=SUBJECT,g=GRADE,b=BOOK,tp=tp,
          w=w,wn=wn,tf=tf,actor=ACTOR,emb=emb,gq=gq)
        lid=f"{SUBJECT}|{GRADE}|{BOOK}|{tp}|{sl}"
        s.run("""MERGE (l:Lesson {lesson_id:$lid})
          SET l.subject_code=$subj,l.grade=$g,l.bo_sach=$b,l.tap_no=$tp,l.work_name=$w,l.work_name_norm=$wn,
              l.title=$w,l.lesson_no=$ln,l.trang_no=$tf,l.trang_from=$tf,l.trang_to=$tt,l.practice_json=$pj,l.ingest_actor=$actor
          WITH l MATCH (k:KnowledgeChunk {uid:$uid}) MERGE (l)-[:HAS_THEORY]->(k)""",
          lid=lid,subj=SUBJECT,g=GRADE,b=BOOK,tp=tp,w=w,wn=wn,ln=c["ln"],tf=tf,tt=tt,pj=pj,actor=ACTOR,uid=uid)
        st["lesson"]+=1
NEO.close()
print(f"\nDONE {SUBJECT} {GRADE} {BOOK}: lessons={st['lesson']} skip={st['skip']}", flush=True)
