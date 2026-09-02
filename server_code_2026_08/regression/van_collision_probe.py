# -*- coding: utf-8 -*-
"""Câu VĂN chứa từ khoá T1 dễ bị hút sang Sử (rủi ro #2). Kỳ vọng: KHÔNG ra hist_fact / lich_su.
Usage: van_collision_probe.py <port>"""
import sys, requests
port = int(sys.argv[1])
QS = ["phong trào Thơ mới là gì", "giảng bài Tây Tiến", "bài thơ Việt Bắc của Tố Hữu nói về chiến dịch nào",
      "vua nào trong truyện Tấm Cám", "phong trào Duy tân trong Ngữ văn 11", "tác phẩm đầu tiên của Nam Cao là gì",
      "hiệp định trong bài Những đứa con trong gia đình", "đọc bài Lượm", "đọc bài Đồng chí", "giảng bài Chiếc lược ngà"]
bad = 0
for i, q in enumerate(QS):
    r = requests.post(f"http://localhost:{port}/v2/rag/retrieve", json={"query": q, "session_id": f"vc_{port}_{i}"}, timeout=40).json()
    it = r.get("intent") or {}; tier = it.get("tier") or it.get("query_type"); subj = it.get("subject")
    flag = "!!" if (tier or "").startswith("hist") or subj in ("lich_su",) else "  "
    bad += flag == "!!"
    print(f"{flag} [{str(tier):16s} subj={str(subj):8s}] {q}")
print(f"\nbị hút sang Sử: {bad}/{len(QS)}  (kỳ vọng 0)")
