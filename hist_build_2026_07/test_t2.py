# -*- coding: utf-8 -*-
import requests
T = [
    ("chiến dịch Điện Biên Phủ trên không diễn ra năm nào", "1972 (không phải 1973)"),
    ("Tạm ước 14 tháng 9 năm 1946 được ký ở đâu", "Paris (không phải Hà Nội)"),
    ("kế hoạch Nava gồm mấy bước", "HAI bước"),
    ("Ai đỗ Trạng nguyên trẻ tuổi nhất lịch sử khoa bảng Việt Nam", "Nguyễn Hiền"),
    ("Tổng bí thư đầu tiên của Đảng Cộng sản Việt Nam là ai", "Trần Phú"),
    ("Xô viết Nghệ Tĩnh diễn ra năm nào", "1930-1931"),
    ("Hiệp định Giơ-ne-vơ được ký ngày nào", "21/7/1954"),
    ("Điện Biên Phủ diễn ra năm nào", ">>> SIBLING GUARD: phải HỎI LẠI"),
    ("Điện Biên Phủ năm 1972 diễn ra thế nào", ">>> có năm -> ra thẳng 1972"),
    ("vì sao ta thắng ở Điện Biên Phủ", ">>> câu GIẢNG: phải đi chunk, KHÔNG abstain"),
    ("đọc bài Nhớ rừng", ">>> REGRESSION: phải RECITE"),
    ("mấy giờ rồi", ">>> REGRESSION: realtime"),
]
for i, (q, exp) in enumerate(T):
    try:
        d = requests.post("http://localhost:8893/v2/rag/retrieve",
                          json={"query": q, "session_id": "t2x_%d" % i}, timeout=40).json()
    except Exception as e:
        print("ERR", q, e); continue
    c = (d.get("context") or "")
    it = d.get("intent", {}) or {}
    tier = it.get("tier") or it.get("query_type")
    head = c[:130].replace("\n", " ")
    print("[%-18s] %s" % (str(tier), q[:48]))
    print("     kỳ vọng: %s" % exp)
    print("     -> %s" % head)
    print()
