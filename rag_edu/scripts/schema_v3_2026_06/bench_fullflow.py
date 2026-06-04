import time, requests, statistics as st
PORTS={"prod_8888":"http://localhost:8888/retrieve"}
# try canary too if up
try:
    if requests.get("http://localhost:8889/health",timeout=3).ok: PORTS["canary_8889"]="http://localhost:8889/retrieve"
except: pass
QUERIES={
 "structured(bài/trang)":[
   ("bài 5 toán lớp 6",{"lop":6,"bo_sach":"KNTT"}),
   ("giải trang 42 toán 9",{"lop":9,"bo_sach":"KNTT"}),
   ("soạn bài 2 ngữ văn 8",{"lop":8,"bo_sach":"KNTT"}),
   ("bài 10 toán 7 trang 30",{"lop":7,"bo_sach":"CTST"}),
 ],
 "concept/explain":[
   ("phân số là gì",{"lop":4,"bo_sach":"KNTT"}),
   ("giải thích tập hợp",{"lop":6,"bo_sach":"KNTT"}),
   ("cách giải phương trình bậc hai",{"lop":9,"bo_sach":"CTST"}),
   ("định lí Pythagore",{"lop":8,"bo_sach":"KNTT"}),
 ],
 "literature/recite":[
   ("soạn bài Bếp lửa",{"lop":8,"bo_sach":"KNTT"}),
   ("đọc thuộc bài Nam quốc sơn hà",{"lop":8,"bo_sach":"KNTT"}),
   ("phân tích Lão Hạc",{"lop":8,"bo_sach":"CD"}),
 ],
}
for pname,url in PORTS.items():
    print(f"\n===== {pname} =====")
    # warmup
    try: requests.post(url,json={"query":"bài 1 toán 6","user_profile":{"lop":6,"bo_sach":"KNTT"}},timeout=30)
    except Exception as e: print("warmup fail",e); continue
    for cat,qs in QUERIES.items():
        lat=[]; tiers=[]
        for q,prof in qs:
            for _ in range(3):
                t=time.time()
                try:
                    r=requests.post(url,json={"query":q,"user_profile":prof},timeout=60).json()
                    lat.append((time.time()-t)*1000)
                    tiers.append((r.get("intent",{}) or {}).get("tier") or (r.get("sources") or ["?"])[0] if r.get("sources") else (r.get("intent",{}) or {}).get("tier","router"))
                except Exception as e: lat.append(60000)
        lat.sort()
        print(f"  {cat:24} p50={lat[len(lat)//2]:6.0f}ms  p95={lat[int(len(lat)*0.95)]:6.0f}ms  mean={st.mean(lat):6.0f}ms  (n={len(lat)})")
