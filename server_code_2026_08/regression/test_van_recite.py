# -*- coding: utf-8 -*-
"""Regression Văn: 'đọc bài <tên>' cho từng bài trong checklist, chấm RECITE/LESSON/MISS.
Usage: test_van_recite.py <port> <cap2|cap3> [items_dir]
Dùng để so prod vs canary TRƯỚC khi deploy (đảm bảo T1/T2 không làm hồi quy Văn)."""
import json, re, sys, os
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
import requests
port = int(sys.argv[1]); cap = sys.argv[2]
d = sys.argv[3] if len(sys.argv) > 3 else os.path.dirname(os.path.abspath(__file__))
items = json.load(open(f"{d}/{cap}_items.json", encoding="utf-8"))
U = f"http://localhost:{port}/v2/rag/retrieve"
def kind(q, sid):
    try: r = requests.post(U, json={"query": q, "session_id": sid}, timeout=30).json()
    except Exception: return "ERR"
    c = r.get("context") or ""; it = r.get("intent") or {}
    if "full_recitation_lines" in c or "[ĐỌC THUỘC" in c or it.get("query_type") == "recite_full_text": return "RECITE"
    if "[ĐỒNG HÀNH" in c or it.get("tier") == "lesson_card": return "LESSON"
    if "KHÔNG TÌM" in c or "chưa tìm thấy dữ liệu" in c or not c.strip(): return "MISS"
    return "OTHER"
def run(i_it):
    i, it = i_it; nm = it["name"]
    k = kind("đọc bài " + nm, f"{cap}_{port}_{i}")
    if k == "MISS":
        base = re.split(r"\s+[-–]\s+", nm)[0].strip()
        if base and base != nm: k = kind("đọc bài " + base, f"{cap}r_{port}_{i}")
    return {**it, "res": k}
with ThreadPoolExecutor(max_workers=6) as ex: res = list(ex.map(run, enumerate(items)))
hit = lambda r: r["res"] in ("RECITE", "LESSON")
print(f"=== VĂN {cap.upper()} @ :{port} ===")
for g in sorted({r["g"] for r in res}):
    sub = [r for r in res if r["g"] == g]; h = sum(map(hit, sub))
    print(f"  Lớp {g}: {h}/{len(sub)} = {100*h//len(sub)}%")
tot = sum(map(hit, res)); print(f"  TỔNG : {tot}/{len(res)} = {100*tot//len(res)}%  {dict(Counter(r['res'] for r in res))}")
json.dump(res, open(f"/tmp/van_{cap}_{port}.json", "w"), ensure_ascii=False)
