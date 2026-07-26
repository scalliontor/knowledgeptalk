# -*- coding: utf-8 -*-
"""Chạy hist_battery trên 1 port: đo context có chứa fact đúng (expect) / bẫy sai (forbid).
PASS = có expect & không forbid. Đây là proxy grounding (context-level), chưa phải câu trả lời LLM."""
import json, sys, requests

port = int(sys.argv[1]); tag = sys.argv[2] if len(sys.argv) > 2 else str(port)
bat = json.load(open("/tmp/hist_battery.json"))
res = []
for i, t in enumerate(bat):
    try:
        d = requests.post(f"http://localhost:{port}/v2/rag/retrieve",
                          json={"query": t["q"], "session_id": f"bat_{tag}_{i}"}, timeout=30).json()
    except Exception:
        res.append((t["id"], "ERR", "")); continue
    craw = (d.get("context") or "")
    # BỎ mục "LƯU Ý TRÁNH NHẦM" trước khi chấm forbid: mục này CỐ Ý chứa con số sai
    # ("không phải 1973") -> nếu không cắt, bộ chấm báo TRAP nhầm (bài học test tuyến != test nội dung).
    craw = craw.split("LƯU Ý TRÁNH NHẦM")[0]
    c = craw.lower()
    # forbid chấm trên phần DỮ KIỆN CHÍNH (tên/Thời gian/Địa điểm), không trên toàn văn:
    # thẻ đúng vẫn được phép nhắc mốc khác có thật (vd ĐBP-trên-không nhắc Hiệp định Paris 1973).
    c_head = craw.split("Các ý chính")[0].lower() if "DỮ KIỆN LỊCH SỬ" in craw else c
    src = "wiki" if "wikipedia" in c else ("miss" if (not c.strip() or "không tìm" in c) else "kb")
    has_e = any(e in c for e in t["expect"])
    has_f = any(f in c_head for f in t["forbid"]) if t["forbid"] else False
    verdict = "PASS" if (has_e and not has_f) else ("TRAP" if has_f else ("MISS" if src == "miss" else "NOFACT"))
    res.append((t["id"], verdict, src))
n = len(res)
p = sum(1 for _, v, _ in res if v == "PASS")
print(f"=== {tag} (:{port}) — PASS {p}/{n} ===")
from collections import Counter
print("  verdict:", dict(Counter(v for _, v, _ in res)))
print("  nguồn khi PASS:", dict(Counter(s for _, v, s in res if v == "PASS")))
print("  -- FAIL --")
for id_, v, s in res:
    if v != "PASS": print(f"   {v:6s} [{s}] {id_}")
json.dump(res, open(f"/tmp/battery_{tag}.json", "w"))
