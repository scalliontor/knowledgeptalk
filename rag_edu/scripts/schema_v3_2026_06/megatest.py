#!/usr/bin/env python3
"""MEGATEST (no subagent, Gemma-FREE) — sinh nhiều case template đa dạng cho MỌI book đã build,
chạy /retrieve canary :8889, chấm anchor/mode/cruft/guard theo dimension. Report per-book + per-dim + fails.
"""
import json, urllib.request, unicodedata, re
from neo4j import GraphDatabase
NEO=GraphDatabase.driver("bolt://localhost:7688",auth=("neo4j",__import__("os").environ.get("EDU_NEO4J_PW","")))
URL="http://localhost:8889/retrieve"
CRUFT=["vietjack","xem lời giải","(giáo viên","video giải","hay nhất, chi tiết","giải bài nhanh với ai","cô ngô"]
CARD={"lesson_card","lesson_practice","lesson_recite"}
def norm(x):
    x=(x or "").replace("đ","d").replace("Đ","D"); x=unicodedata.normalize("NFD",x)
    return "".join(c for c in x if unicodedata.category(c)!="Mn").lower().strip()
def nodia(s):  # bỏ dấu, giả lập gõ không dấu
    s=(s or "").replace("đ","d").replace("Đ","D"); s=unicodedata.normalize("NFD",s)
    return "".join(c for c in s if unicodedata.category(c)!="Mn")
def post(q,p):
    try:
        body=json.dumps({"query":q,"user_profile":p}).encode()
        r=urllib.request.Request(URL,data=body,headers={"Content-Type":"application/json"})
        return json.loads(urllib.request.urlopen(r,timeout=30).read())
    except Exception: return {}

EXPLAIN=["giảng bài này cho em","giải thích giúp em bài này với","phân tích bài này đi","nội dung chính của bài này là gì","cho em hiểu bài này","tóm tắt bài này giúp em","bài này nói về điều gì vậy ạ"]
EXPLAIN_TYPO=["giag bai nay di","giai thik dum em bai nay","bai nay noi j the ad","phan tic bai nay vs","giup e hieu bai nay voi"]
PRACTICE=["cho em vài bài luyện tập với","bài này có bài tập nào không ạ","luyện tập bài này đi","cho em mấy câu ôn tập","thực hành bài này thế nào"]
RECITE=["đọc thuộc bài này cho em","đọc diễn cảm bài này","đọc nguyên văn bài thơ này","ngâm bài thơ này nghe"]
NAMEQ=["giảng bài {w} cho em","bài {w} nói về gì","phân tích {w} giúp em","cho em hiểu {w}"]
OOB={  # works/khái niệm KHÔNG thuộc sách (lớp/môn khác) -> phải KHÔNG ra card
 "ngu_van":["Nhớ rừng","Lặng lẽ Sa Pa","Tắt đèn","Chiếc lược ngà","Lão Hạc"],
 "toan":["đạo hàm","tích phân","số phức","ma trận","giới hạn dãy số"],
 "khtn":["quang hợp ở thực vật","cấu tạo tế bào","sự nở vì nhiệt","lực ma sát là gì"],
 "lich_su":["khởi nghĩa Lam Sơn","Ngô Quyền và chiến thắng Bạch Đằng","nhà nước Văn Lang"],
 "dia_li":["khí hậu châu Phi","sông ngòi châu Á","dân cư châu Âu"],
 "gdcd":["quyền trẻ em","tự lập","tiết kiệm là gì","yêu thương con người"],
}
CHITCHAT=["hôm nay trời đẹp nhỉ","kể cho tớ một chuyện cười đi","mấy giờ rồi bạn ơi","bạn tên gì thế","chán quá làm gì giờ"]
OFFTOPIC=["thủ đô nước Pháp là gì","cách nấu phở bò ngon","giá vàng hôm nay bao nhiêu","messi đá cho đội nào"]
TRAP=["trang phục của nhân vật ra sao","cách trang trí lớp học","sự kiện nổi bật năm 1945","ý nghĩa con số 100"]

with NEO.session() as s:
    books=s.run("MATCH (l:Lesson) RETURN l.subject_code AS s,l.grade AS g,l.bo_sach AS b,count(*) AS n ORDER BY s,g,b").data()

cases=[]; idc=0
def add(q,prof,ew,em,guard,dim):
    global idc; idc+=1
    cases.append({"id":idc,"query":q,"profile":prof,"expected_work":ew,"expected_mode":em,"is_guard":guard,"dimension":dim,"_book":bkkey})

for bk in books:
    subj,g,b=bk["s"],bk["g"],bk["b"]; bkkey=f"{subj}|{g}|{b}"
    with NEO.session() as s:
        works=s.run("MATCH (l:Lesson {subject_code:$s,grade:$g,bo_sach:$b}) RETURN l.work_name AS w,l.trang_from AS tf,l.tap_no AS tap ORDER BY coalesce(l.tap_no,0),coalesce(l.trang_from,9999)",s=subj,g=g,b=b).data()
    # sample tối đa 12 work đều khắp
    if len(works)>6:
        step=len(works)/6.0; works=[works[int(i*step)] for i in range(6)]
    base=lambda **k: dict(lop=g,bo_sach=b,subject=subj,**k)
    for i,wr in enumerate(works):
        w=wr["w"]; tf=wr["tf"]; tap=wr["tap"]
        add(EXPLAIN[i%len(EXPLAIN)], base(current_lesson=w), w,"lesson_card",False,"current_lesson")
        add(EXPLAIN_TYPO[i%len(EXPLAIN_TYPO)], base(current_lesson=w), w,"lesson_card",False,"typo_teen")
        add(PRACTICE[i%len(PRACTICE)], base(current_lesson=w), w,"lesson_practice",False,"practice")
        if tf: add("giảng bài trang %d"%tf, base(tap=tap), w,"lesson_card",False,"trang_query")
        # name in query (no current_lesson) — chỉ khi tên đủ đặc trưng (>=8 ký tự, không phải 'Em làm được...')
        if len(w)>=8 and not w.lower().startswith(("em làm","ôn tập","thực hành")):
            add(NAMEQ[i%len(NAMEQ)].format(w=w), base(), w,"lesson_card",False,"name_query")
        if subj=="ngu_van" and i%3==0:
            add(RECITE[i%len(RECITE)], base(current_lesson=w), w,"lesson_recite",False,"recite")
    # guards
    for q in CHITCHAT[:3]: add(q, base(), None,None,True,"guard_chitchat")
    for q in OFFTOPIC[:2]: add(q, base(), None,None,True,"guard_offtopic")
    for q in OOB.get(subj,[])[:3]: add("giảng bài %s cho em"%q, base(), None,None,True,"guard_out_of_book")
    add("giảng bài trang 999 cho em", base(), None,None,True,"guard_oob_trang")
    add("bài ở trang 888 nói gì", base(), None,None,True,"guard_oob_trang")
    for q in TRAP[:3]: add(q, base(), None,None,True,"guard_trap")

# run + score
print("START cases=%d"%len(cases),flush=True)
agg={"anchor_ok":0,"anchor_tot":0,"mode_ok":0,"guard_ok":0,"guard_tot":0,"cruft":0}
bydim={}; bybook={}; fails=[]
for ci,c in enumerate(cases):
    if ci%40==0: print("[run] %d/%d"%(ci,len(cases)),flush=True)
    r=post(c["query"],c["profile"])
    it=r.get("intent",{}) or {}; tier=it.get("tier","none"); work=it.get("work_name","") or ""
    ctx=(r.get("context","") or "").lower(); cruft=tier in CARD and any(x in ctx for x in CRUFT)
    d=bydim.setdefault(c["dimension"],{"ok":0,"tot":0}); bk=bybook.setdefault(c["_book"],{"ok":0,"tot":0,"cruft":0})
    if cruft: agg["cruft"]+=1; bk["cruft"]+=1
    if c["is_guard"]:
        agg["guard_tot"]+=1; d["tot"]+=1; bk["tot"]+=1
        ok=tier not in CARD
        agg["guard_ok"]+=ok; d["ok"]+=ok; bk["ok"]+=ok
        if not ok: fails.append({"book":c["_book"],"dim":c["dimension"],"q":c["query"][:45],"got":tier+":"+work[:24]})
    else:
        agg["anchor_tot"]+=1; d["tot"]+=1; bk["tot"]+=1
        a=tier in CARD and norm(work)==norm(c["expected_work"])
        agg["anchor_ok"]+=a; d["ok"]+=a; bk["ok"]+=a
        if a and (not c["expected_mode"] or tier==c["expected_mode"]): agg["mode_ok"]+=1
        if not a: fails.append({"book":c["_book"],"dim":c["dimension"],"q":c["query"][:45],"exp":(c["expected_work"] or "")[:24],"got":tier+":"+work[:24]})
NEO.close()
out={"total":len(cases),"agg":agg,
 "anchor_pct":round(100*agg["anchor_ok"]/max(1,agg["anchor_tot"]),1),
 "mode_pct":round(100*agg["mode_ok"]/max(1,agg["anchor_tot"]),1),
 "guard_pct":round(100*agg["guard_ok"]/max(1,agg["guard_tot"]),1),
 "by_dim":{k:{"pct":round(100*v["ok"]/max(1,v["tot"]),1),"tot":v["tot"]} for k,v in sorted(bydim.items())},
 "by_book":{k:{"pct":round(100*v["ok"]/max(1,v["tot"]),1),"tot":v["tot"],"cruft":v["cruft"]} for k,v in sorted(bybook.items())},
 "fails":fails}
print(json.dumps(out,ensure_ascii=False,indent=1))
