#!/usr/bin/env python3
"""BACKTEST RULE — 500-câu/quyển sách cho companion Lesson Card.
Usage: backtest_book.py <subject> <grade> <book> <tap> <N> <port>
Pull :Lesson (ground truth) -> Gemma sinh paraphrase student-voice phủ {dimension×intent} + adversarial
-> chạy /retrieve -> chấm anchor/mode/cruft/guard + latency P50/P95. Output JSON + bảng.
"""
import sys, json, time, re, urllib.request, unicodedata, statistics, random
from neo4j import GraphDatabase

SUBJECT = sys.argv[1] if len(sys.argv)>1 else "ngu_van"
GRADE   = int(sys.argv[2]) if len(sys.argv)>2 else 9
BOOK    = sys.argv[3] if len(sys.argv)>3 else "CTST"
TAP     = int(sys.argv[4]) if len(sys.argv)>4 else 2
N       = int(sys.argv[5]) if len(sys.argv)>5 else 500
PORT    = sys.argv[6] if len(sys.argv)>6 else "8889"
random.seed(42)  # deterministic assembly

NEO=GraphDatabase.driver("bolt://localhost:7688",auth=("neo4j",__import__("os").environ.get("EDU_NEO4J_PW","")))
URL=f"http://localhost:{PORT}/retrieve"
GEMMA_URL="http://localhost:8080/v1/chat/completions"; GKEY=__import__("os").environ.get("GEMMA_KEY","")
CRUFT=["vietjack","xem lời giải","giáo viên","video giải","hay nhất, chi tiết","cô ngô"]

def gemma(sys_p, usr, mx=1400):
    body=json.dumps({"model":"gemma-4","messages":[{"role":"system","content":sys_p},{"role":"user","content":usr}],"temperature":0.7,"max_tokens":mx}).encode()
    r=urllib.request.Request(GEMMA_URL,data=body,headers={"Authorization":f"Bearer {GKEY}","Content-Type":"application/json"})
    return json.loads(urllib.request.urlopen(r,timeout=120).read())["choices"][0]["message"]["content"]

# ── 1. ground truth lessons ──
with NEO.session() as s:
    rows=s.run("""MATCH (l:Lesson {subject_code:$s,grade:$g,bo_sach:$b})
        WHERE ($tap IS NULL OR l.tap_no=$tap)
        OPTIONAL MATCH (l)-[:HAS_THEORY]->(t) OPTIONAL MATCH (l)-[:HAS_RECITE]->(r)
        RETURN l.work_name AS work, l.trang_from AS tf, l.trang_to AS tt,
               count(DISTINCT r) AS recite, l.practice_json AS pj, collect(t.text)[0] AS theory""",
        s=SUBJECT,g=GRADE,b=BOOK,tap=TAP).data()
L=[r for r in rows if r["work"]]
print(f"[backtest] {len(L)} lessons for {SUBJECT} {GRADE} {BOOK} tap{TAP}", flush=True)
maxtrang=max((r["tt"] or 0) for r in L) if L else 200

GEN_SYS=("Bạn tạo câu hỏi GIỌNG HỌC SINH thật (ngắn, tự nhiên, đa dạng cách nói, có thể thiếu dấu/teen) để test trợ lý học tập. "
"Chỉ trả JSON. KHÔNG giải thích.")
def gen_for(lesson):
    has_recite = lesson["recite"]>0
    has_prac = bool(lesson["pj"])
    theory=(lesson["theory"] or "")[:1200]
    usr=(f"BÀI: {lesson['work']}\nMÔN: {SUBJECT} lớp {GRADE}\nNỘI DUNG (để bạn mô tả gián tiếp):\n{theory}\n\n"
         "Trả JSON các MẢNG câu hỏi giọng học sinh:\n"
         '{"explain":[12 câu xin GIẢNG/giải thích/hiểu bài, KHÔNG nêu tên bài, kiểu "giảng bài này đi","phân tích giúp em"],'
         '"content_only":[8 câu MÔ TẢ nội dung/đặc điểm bài để hỏi, TUYỆT ĐỐI KHÔNG nêu tên bài/tác giả],'
         '"name_mention":[6 câu CÓ nêu tên bài/tác phẩm rõ ràng],'
         + ('"practice":[7 câu xin LÀM BÀI TẬP/luyện tập/ôn],' if has_prac else '"practice":[],')
         + ('"recite":[6 câu xin ĐỌC THUỘC/đọc diễn cảm/đọc nguyên văn]' if has_recite else '"recite":[]')
         + "}")
    try:
        raw=gemma(GEN_SYS,usr).replace("```json","").replace("```","").strip()
        m=re.search(r"\{.*\}",raw,re.S); d=json.loads(m.group(0) if m else raw)
        return d
    except Exception as e:
        print(f"  gen ERR {lesson['work'][:30]}: {e}", flush=True); return {}

# ── 2. assemble cases ──
cases=[]  # (query, profile, expect_work, expect_mode, dim)
base=lambda **k: dict(lop=GRADE,bo_sach=BOOK,subject=SUBJECT,**k)
for les in L:
    g=gen_for(les); w=les["work"]; tf,tt=les["tf"],les["tt"]
    ex,co,nm,pr,re_=g.get("explain",[]),g.get("content_only",[]),g.get("name_mention",[]),g.get("practice",[]),g.get("recite",[])
    # current_lesson dim (generic explain)
    for q in ex[:5]: cases.append((q, base(current_lesson=w), w, "lesson_card","current_lesson"))
    # trang in query
    if tf:
        for q in ex[5:9]:
            p=random.randint(tf,tt or tf); cases.append((f"{q} ở trang {p}", base(), w, "lesson_card","trang_query"))
    # trang in profile
    if tf:
        for q in ex[9:12]:
            p=random.randint(tf,tt or tf); cases.append((q, base(trang=p), w, "lesson_card","trang_profile"))
    # name in query
    for q in nm[:6]: cases.append((q, base(), w, "lesson_card","name_query"))
    # content-only (hard)
    for q in co[:6]: cases.append((q, base(), w, "lesson_card","content_only"))
    # practice
    for q in pr[:6]: cases.append((q, base(current_lesson=w), w, "lesson_practice","practice"))
    # recite
    for q in re_[:6]: cases.append((q, base(current_lesson=w), w, "lesson_recite","recite"))

# ── 3. adversarial / guards (~15%) ──
GUARDS=[
 ("hôm nay trời đẹp nhỉ", base(), None,"none","guard_chitchat"),
 ("kể cho tớ một câu chuyện cười", base(), None,"none","guard_chitchat"),
 ("mấy giờ rồi bạn ơi", base(), None,"none","guard_chitchat"),
 ("bạn tên gì thế", base(), None,"none","guard_chitchat"),
 ("giảng bài trang 999 cho tớ", base(), None,"noncard","guard_oob_trang"),
 ("bài ở trang 888 nói gì", base(), None,"noncard","guard_oob_trang"),
 ("trang phục của nhân vật thế nào", base(), None,"noncard","guard_trap_word"),
 ("sự kiện năm 1945 có gì", base(), None,"noncard","guard_trap_year"),
 ("công thức hoá học của nước là gì", base(), None,"noncard","guard_offtopic"),
 ("thủ đô nước Pháp là gì", base(), None,"noncard","guard_offtopic"),
]
# cross-grade / out-of-book named work (not in this book)
for badname in ["Nhớ rừng","Lặng lẽ Sa Pa","Chiếc lược ngà"]:
    GUARDS.append((f"giảng bài {badname} cho em", base(), None,"noncard","guard_out_of_book"))

n_guard=max(1,int(N*0.15))
guards=(GUARDS*((n_guard//len(GUARDS))+1))[:n_guard]
# trim/pad lesson cases to N - n_guard
random.shuffle(cases)
lesson_cases=cases[:N-n_guard]
allc=lesson_cases+[ (q,p,w,m,d) for (q,p,w,m,d) in guards ]
print(f"[backtest] assembled {len(allc)} cases ({len(lesson_cases)} lesson + {len(guards)} guard)", flush=True)

# ── 4. run + score + latency ──
def post(q,p):
    body=json.dumps({"query":q,"user_profile":p}).encode()
    r=urllib.request.Request(URL,data=body,headers={"Content-Type":"application/json"})
    t0=time.time(); resp=json.loads(urllib.request.urlopen(r,timeout=30).read()); return resp,(time.time()-t0)*1000

def norm(x):
    x=(x or "").replace("đ","d").replace("Đ","D"); x=unicodedata.normalize("NFD",x)
    return "".join(c for c in x if unicodedata.category(c)!="Mn").lower().strip()

CARD_TIERS={"lesson_card","lesson_practice","lesson_recite"}
res={"anchor_ok":0,"mode_ok":0,"cruft":0,"guard_ok":0,"err":0}
bydim={}; lat=[]; fails=[]
for i,(q,p,ew,em,dim) in enumerate(allc):
    try: resp,ms=post(q,p)
    except Exception as e: res["err"]+=1; continue
    lat.append(ms)
    it=resp.get("intent",{}) or {}; ctx=resp.get("context","") or ""
    tier=it.get("tier","none"); work=it.get("work_name","")
    cruft=any(c in ctx.lower() for c in CRUFT)
    d=bydim.setdefault(dim,{"n":0,"anchor":0,"mode":0,"cruft":0})
    d["n"]+=1
    if cruft and tier in CARD_TIERS: res["cruft"]+=1; d["cruft"]+=1
    if ew is None:  # guard
        good = tier not in CARD_TIERS
        res["guard_ok"]+= 1 if good else 0; d["anchor"]+= 1 if good else 0
        if not good and len(fails)<40: fails.append((dim,q[:40],f"FALSE CARD: {work[:25]}"))
    else:
        a = (norm(work)==norm(ew)); res["anchor_ok"]+=1 if a else 0; d["anchor"]+=1 if a else 0
        m = a and (tier==em); res["mode_ok"]+=1 if m else 0; d["mode"]+=1 if m else 0
        if not a and len(fails)<40: fails.append((dim,q[:40],f"got {tier}:{work[:22]} exp {ew[:22]}"))
    if (i+1)%50==0: print(f"  ...{i+1}/{len(allc)}", flush=True)

nL=sum(1 for c in allc if c[2] is not None); nG=len(allc)-nL
P=lambda v: round(statistics.quantiles(lat,n=100)[v-1],1) if len(lat)>=100 else round(max(lat),1)
report={
 "book":f"{SUBJECT} {GRADE} {BOOK} tap{TAP}","port":PORT,"total":len(allc),"lessons":len(L),
 "lesson_cases":nL,"guard_cases":nG,"errors":res["err"],
 "anchor_acc":round(100*res["anchor_ok"]/max(1,nL),1),
 "mode_acc":round(100*res["mode_ok"]/max(1,nL),1),
 "guard_acc":round(100*res["guard_ok"]/max(1,nG),1),
 "cruft_on_cards":res["cruft"],
 "latency_ms":{"p50":round(statistics.median(lat),1) if lat else 0,"p95":P(95),"p99":P(99),"max":round(max(lat),1) if lat else 0},
 "by_dimension":{k:{"n":v["n"],"anchor%":round(100*v["anchor"]/max(1,v["n"]),1),"mode%":round(100*v["mode"]/max(1,v["n"]),1),"cruft":v["cruft"]} for k,v in sorted(bydim.items())},
 "sample_fails":fails[:30],
}
json.dump(report, open(f"/tmp/backtest_{SUBJECT}_{GRADE}_{BOOK}_t{TAP}.json","w"), ensure_ascii=False, indent=1)
NEO.close()
print("\n"+"="*70+"\nBACKTEST REPORT\n"+"="*70)
print(json.dumps({k:v for k,v in report.items() if k!="sample_fails"}, ensure_ascii=False, indent=1))
print("\n--- sample fails ---")
for d,q,info in fails[:25]: print(f"  [{d}] {q!r} -> {info}")
print(f"\nSAVED /tmp/backtest_{SUBJECT}_{GRADE}_{BOOK}_t{TAP}.json")
