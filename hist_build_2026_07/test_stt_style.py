# -*- coding: utf-8 -*-
"""Test T2 với câu kiểu STT THẬT (không phải gõ tay sạch):
 - năm đọc thành chữ: 'một chín bảy hai', 'năm bảy hai'
 - sai chính tả/thiếu dấu do nhận dạng giọng
 - tên phiên âm rời rạc
Đây là bài học critique #1: test gõ tay sẽ PASS giả."""
import requests

CASES = [
    # (câu kiểu STT, kỳ vọng)
    ("điện biên phủ trên không năm một chín bảy hai", "1972"),
    ("chiến dịch điện biên phủ trên không diễn ra khi nào", "1972"),
    ("dien bien phu tren khong nam nao", "1972 (không dấu)"),
    ("tạm ước mười bốn tháng chín ký ở đâu", "Pa-ri"),
    ("kế hoạch na va có mấy bước", "2 bước (tên tách rời)"),
    ("kế hoạch nà và gồm mấy bước", "2 bước (STT sai dấu)"),
    ("hiệp định giơ ne vơ ký ngày nào", "21/7/1954 (không gạch nối)"),
    ("xô viết nghệ tĩnh năm nào", "1930-1931"),
    ("ai là tổng bí thư đầu tiên", "Trần Phú"),
    ("trạng nguyên trẻ nhất là ai", "Nguyễn Hiền"),
    ("vua nào trị vì ngắn nhất", "Dục Đức"),
    ("hồng quân liên xô thành lập khi nào", "1918"),
    ("điện biên phủ năm một chín năm tư", "1954 (năm đọc chữ)"),
]
ok = 0
for i, (q, exp) in enumerate(CASES):
    try:
        d = requests.post("http://localhost:8893/v2/rag/retrieve",
                          json={"query": q, "session_id": "stt_%d" % i}, timeout=40).json()
    except Exception as e:
        print("ERR", q, e); continue
    c = (d.get("context") or "")
    it = d.get("intent", {}) or {}
    tier = it.get("tier") or it.get("query_type")
    hit = tier in ("hist_fact", "hist_fact_clarify")
    ok += hit
    mark = "✓" if hit else "·"
    print("%s [%-18s] %-46s | mong: %s" % (mark, str(tier), q[:46], exp))
    if hit:
        print("      -> %s" % c[:100].replace("\n", " "))
print("\nvào fact-node: %d/%d" % (ok, len(CASES)))
