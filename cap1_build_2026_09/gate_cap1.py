# -*- coding: utf-8 -*-
"""Cổng TẤT ĐỊNH cho dữ liệu bù CẤP 1 (không dùng LLM) — chạy TRƯỚC khi ingest.

Hai loại thẻ, hai bộ luật khác hẳn nhau:

RECITE (đọc nguyên văn) — chỉ cho phép tác phẩm CÔNG CỘNG:
  R1 có full_text đủ dài, không rỗng
  R2 KHÔNG dính rác trang soạn-bài ('Câu 1', 'Trả lời:', 'Nội dung chính', 'Bố cục'…)
     — đây là lỗi đã làm hỏng 60% dữ liệu đợt tiểu học 07/03
  R3 KHÔNG lẫn HTML / chú thích số [1] / đuôi metadata
  R4 lý do công cộng phải nêu căn cứ (dân gian/cổ tích/ngụ ngôn/ca dao/đồng dao/
     truyện cổ/phạm vi công cộng/năm mất tác giả) — không có = FLAG cho người xem
  R5 >= 2 nguồn độc lập (đối chiếu bản chép), và không được CHỈ có nguồn soạn-bài

COMPANION (tự viết giảng, KHÔNG chép):
  C1 full_text PHẢI rỗng — có chữ nào là nghi chép nguyên văn
  C2 tóm tắt >= 80 ký tự, ý nghĩa >= 40, >= 3 câu hỏi và câu hỏi phải kết thúc bằng '?'
  C3 KHÔNG dính rác soạn-bài
  C4 không có đoạn trong ngoặc kép dài > 60 ký tự (dấu hiệu chép nguyên văn lén)
  C5 tóm tắt không được có dáng THƠ (>=3 dòng ngắt dòng) — dạng đó là chép khổ thơ

CHUNG: tên bài phải nằm trong danh sách thiếu (không bịa bài), bộ sách hợp lệ, không trùng.
Output: cap1_gated.json / cap1_flagged.json"""
import glob, json, os, re, sys, unicodedata
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
SOAN_SITE = ("loigiaihay", "vietjack", "vndoc", "tech12h", "hoc247", "hoidap", "lazi",
             "tailieu", "download.vn", "hoatieu", "thuthuat")
# CHỈ bắt "đồ đạc của trang web soạn bài", KHÔNG bắt từ tiếng Việt thường:
# 'luyện tập'/'bài tập'/'gợi ý' xuất hiện hợp lệ trong chính văn bản
# ("Lời kêu gọi toàn dân tập thể dục" nói về luyện tập) -> loại khỏi luật.
CRUFT = re.compile(
    r"(câu\s*\d+\s*[:.）)]|trả lời\s*:|soạn bài|nội dung chính|bố cục\s*:|tác giả\s*:|"
    r"trắc nghiệm|xem thêm|phương pháp giải|lời giải chi tiết|đáp án\s*:|giải sgk|"
    r"từ khóa\s*:|tags?\s*:)", re.I)
HTMLISH = re.compile(r"(<[a-z/][^>]{0,40}>|&nbsp;|&amp;|&quot;|\[\d{1,2}\])")
PD_REASON = re.compile(
    r"(dân gian|cổ tích|ngụ ngôn|ca dao|đồng dao|tục ngữ|vè\b|truyện cổ|thần thoại|"
    r"truyền thuyết|phạm vi công cộng|public domain|mất năm 1[0-9]{3}|mất 1[0-9]{3}|"
    r"qua đời năm 1[0-9]{3})", re.I)
BO_SACH_OK = {"KNTT", "CTST", "CD", "Cánh Diều", "Kết nối tri thức", "Chân trời sáng tạo",
              "SGK cũ", "Sách cũ", "sách cũ", "cũ", "2006", "CŨ"}
# Rác trong phần TỰ VIẾT chỉ tính các dấu hiệu CHÉP TRANG SOẠN-BÀI thật sự;
# 'gợi ý'/'hướng dẫn' là từ bình thường khi giáo viên tự viết -> không tính.
CRUFT_WRITTEN = re.compile(
    r"(câu\s*\d+\s*[:.）)]|trả lời\s*:|soạn bài|nội dung chính|bố cục|trắc nghiệm|"
    r"xem thêm|lời giải chi tiết|đáp án|giải sgk|phương pháp giải|tags?\s*:)", re.I)


def fold(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").replace("đ", "d")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s)).strip()


items = []
for f in sorted(glob.glob(f"{HERE}/out/*.json")):
    d = json.load(open(f, encoding="utf-8"))
    lst = d if isinstance(d, list) else (d.get("items") or d.get("results") or [])
    for it in lst:
        it["_file"] = os.path.basename(f)
        it.setdefault("grade", d.get("grade") if isinstance(d, dict) else None)
        items.append(it)
print(f"vào: {len(items)} bài từ {len(set(i['_file'] for i in items))} file")

want = set()
for fn in ("cap1_missing.json", "cap1_todo.json"):
    p = f"{HERE}/{fn}"
    if os.path.exists(p):
        for x in json.load(open(p, encoding="utf-8")):
            want.add(fold(x.get("ten_bai") or x.get("name") or ""))
print(f"danh sách bài thiếu (đối chiếu chống bịa bài): {len(want)}")

gated, flagged, reasons = [], [], Counter()
seen = {}
for it in items:
    e = []
    name = (it.get("ten_bai") or "").strip()
    kind = (it.get("kind") or "").lower()
    ft = (it.get("full_text") or "").strip()
    comp = it.get("companion") or {}
    srcs = [s for s in (it.get("sources") or []) if isinstance(s, str)]
    ly_do = it.get("ly_do") or ""
    nf = fold(name)

    if len(name) < 2:
        e.append("tên-rỗng")
    elif want and nf not in want:
        e.append("tên KHÔNG có trong danh sách thiếu")
    if nf in seen and seen[nf] != it["_file"]:
        e.append(f"TRÙNG với {seen[nf]}")
    else:
        seen[nf] = it["_file"]
    if (it.get("bo_sach") or "").strip() not in BO_SACH_OK:
        e.append(f"bộ sách lạ({it.get('bo_sach')})")
    if not srcs:
        e.append("không nguồn")

    if kind == "recite":
        if len(ft) < 40:
            e.append(f"full_text quá ngắn({len(ft)})")
        if CRUFT.search(ft):
            e.append(f"RÁC soạn-bài trong nguyên văn({CRUFT.search(ft).group(0)[:22]!r})")
        if HTMLISH.search(ft):
            e.append(f"HTML/chú-thích lẫn vào({HTMLISH.search(ft).group(0)[:16]!r})")
        if not PD_REASON.search(ly_do):
            e.append("thiếu căn cứ CÔNG CỘNG trong ly_do")
        if len(srcs) < 2:
            e.append(f"recite chỉ {len(srcs)} nguồn (cần >=2 để đối chiếu)")
        if srcs and all(any(s in u for s in SOAN_SITE) for u in srcs):
            e.append("recite CHỈ có nguồn soạn-bài")
    elif kind == "companion":
        if ft:
            e.append(f"companion mà CÓ full_text({len(ft)} ký tự) -> nghi chép nguyên văn")
        tt = (comp.get("tom_tat") or "").strip()
        yn = (comp.get("y_nghia") or "").strip()
        ch = [c for c in (comp.get("cau_hoi") or []) if isinstance(c, str) and c.strip()]
        if len(tt) < 80:
            e.append(f"tóm tắt ngắn({len(tt)})")
        if len(yn) < 40:
            e.append(f"ý nghĩa ngắn({len(yn)})")
        if len(ch) < 3:
            e.append(f"câu hỏi={len(ch)}")
        elif not any(c.strip().endswith("?") for c in ch):
            # câu khiến ('Em hãy kể lại…') vẫn hợp lệ, nhưng phải có ÍT NHẤT 1 câu hỏi thật
            e.append("không có câu hỏi nào kết thúc bằng '?'")
        elif any(len(c.strip()) < 12 for c in ch[:3]):
            e.append("câu hỏi quá ngắn")
        blob = " ".join([tt, yn, comp.get("nhan_vat") or ""])
        if CRUFT_WRITTEN.search(blob):
            e.append(f"RÁC soạn-bài trong phần giảng({CRUFT_WRITTEN.search(blob).group(0)[:22]!r})")
        m = re.search(r"[\"“”'‘’]([^\"“”]{60,})[\"“”'‘’]", blob)
        if m:
            e.append(f"trích nguyên văn dài trong ngoặc kép({len(m.group(1))} ký tự)")
        if tt.count("\n") >= 3:
            e.append("tóm tắt có dáng THƠ (>=3 dòng) -> nghi chép khổ thơ")
    elif kind == "skip":
        pass
    else:
        e.append(f"kind lạ({kind!r})")

    if e:
        it["_errs"] = e
        flagged.append(it)
        for x in e:
            reasons[x.split("(")[0].strip()] += 1
    else:
        gated.append(it)

json.dump(gated, open(f"{HERE}/cap1_gated.json", "w"), ensure_ascii=False, indent=1)
json.dump(flagged, open(f"{HERE}/cap1_flagged.json", "w"), ensure_ascii=False, indent=1)

print(f"\n=== CỔNG CẤP 1 ===")
print(f"  ĐẠT  : {len(gated)}   {dict(Counter(i.get('kind') for i in gated))}")
print(f"  FLAG : {len(flagged)}")
for k, v in reasons.most_common():
    print(f"      {v:4d}  {k}")
print(f"\n  theo lớp (đạt):", dict(sorted(Counter(i.get('grade') for i in gated).items(), key=lambda x: str(x[0]))))
print("\n  -- 15 ca FLAG đầu --")
for it in flagged[:15]:
    print(f"    L{it.get('grade')} {(it.get('ten_bai') or '')[:34]:<36} [{it.get('kind')}] {it['_errs'][:2]}")
