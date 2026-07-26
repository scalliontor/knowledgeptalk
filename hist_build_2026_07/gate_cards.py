# -*- coding: utf-8 -*-
"""Cổng TẤT ĐỊNH cho fact-card raw (không dùng LLM).
A) sanity schema/format
B) TỰ NHẤT QUÁN (mạnh nhất, không cần biết đáp án): năm trong TÊN phải khớp field year/date range;
   năm trong date_start/end phải bao year; facts phải nhắc lại year.
C) KNOWN-FACT: chỉ áp khi tên thẻ KHỚP CHÍNH XÁC khoá (tránh false-positive kiểu 'nhà Trần đắp đê' vs 1226).
D) collision: cụm dễ nhầm phải có qualifier; phát hiện trùng name khác year.
Output: cards_gated.json / cards_flagged.json"""
import glob, json, re, unicodedata
from collections import Counter, defaultdict

SP = "/tmp/claude-1000/-mnt-DA0054DE0054C365-STEAM-LAB-cloud-ptalk-Knowledgeforptalk/11f820bc-4da0-49cc-aa18-4c452d393474/scratchpad"

def fold(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").replace("đ", "d")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s)).strip()

# C) chỉ các ca EXACT-NAME quan trọng (collision / lỗi user đã gặp)
KNOWN_EXACT = {
    "chien dich dien bien phu tren khong": 1972,
    "dien bien phu tren khong": 1972,
    "chien dich dien bien phu": 1954,
    "cong xa pa ri": 1871,
    "cach mang thang muoi nga": 1917,
    "khoi nghia xi pay": 1857,
    "hoi viet nam cach mang thanh nien": 1925,
    "xo viet nghe tinh": 1930,
    "phong trao xo viet nghe tinh": 1930,
    "tam uoc viet phap": 1946,
    "hiep dinh gio ne vo": 1954,
    "hiep dinh pa ri": 1973,
    "chien dich viet bac thu dong": 1947,
    "chien dich bien gioi": 1950,
    "ke hoach nava": 1953,
    "nam bo khang chien": 1945,
    "chien dich ho chi minh": 1975,
    "chien thang bach dang": 938,
}
COLLISION_STEMS = ["dien bien phu", "khang chien chong tong", "khang chien chong mong nguyen",
                   "hiep dinh", "dai hoi dai bieu toan quoc", "chien tranh the gioi", "cach mang tu san"]
BANNED = re.compile(r"soạn bài|trắc nghiệm|lời giải|đọc hiểu|giáo án|bài tập", re.I)
KINDS = {"event","campaign","battle","treaty","movement","person","dynasty","period","org","artifact","place","concept"}
YEAR_RE = re.compile(r"\b(\d{3,4})\s*(tcn|trước công nguyên)?\b", re.I)

def years_in(text):
    """Năm 3-4 chữ số trong text; TCN -> âm."""
    out = []
    for m in re.finditer(r"(\d{3,4})\s*(TCN|tcn|trước Công nguyên|trước công nguyên)?", text or ""):
        y = int(m.group(1))
        if m.group(2): y = -y
        if -3000 <= y <= 2030: out.append(y)
    return out

def date_year(d):
    """Rút năm từ date_start/end: hỗ trợ '-179', '179 TCN', '1954-05-07', '12/1950'."""
    if not d or not isinstance(d, str): return None
    s = d.strip()
    neg = bool(re.search(r"tcn|trước công nguyên|bc", s, re.I)) or s.startswith("-")
    # ISO yyyy-mm-dd -> lấy nhóm 4 chữ số đầu; dd/mm/yyyy -> lấy nhóm 4 chữ số
    m = re.search(r"\b(\d{4})\b", s) or re.search(r"\b(\d{1,4})\b", s)
    if not m: return None
    y = int(m.group(1))
    return -y if neg else y

cards = []
for f in sorted(glob.glob(f"{SP}/histcards_raw/raw_g*_c*.json")):
    d = json.load(open(f))
    for c in d.get("cards", []):
        c["_grade"] = d.get("grade"); c["_chunk"] = d.get("chunk")
        cards.append(c)

gated, flagged = [], []
reasons = Counter()
for c in cards:
    errs = []
    name = (c.get("name") or "").strip()
    y = c.get("year")
    ds, de = date_year(c.get("date_start")), date_year(c.get("date_end"))

    # A) format
    if len(name) < 2: errs.append("name-rỗng")
    if BANNED.search(name + " " + (c.get("summary") or "")): errs.append("cruft-soạn-bài")
    if c.get("kind") not in KINDS: c["kind"] = "event"
    facts = c.get("facts") or []
    if not (3 <= len(facts) <= 12): errs.append(f"facts={len(facts)}")
    elif not all(isinstance(f, str) and 20 <= len(f) <= 400 for f in facts): errs.append("fact-độ-dài")
    if not any(isinstance(s, str) and (s.startswith("http") or s.startswith("wikidata")) for s in (c.get("sources") or [])):
        errs.append("thiếu-nguồn")
    if y is not None and not (isinstance(y, int) and -3000 <= y <= 2030): errs.append("year-vô-lý")

    # B) tự nhất quán
    nyears = years_in(name)
    if nyears and y is not None:
        lo, hi = min(nyears), max(nyears)
        span_lo = min([v for v in (y, ds, de) if v is not None])
        span_hi = max([v for v in (y, ds, de) if v is not None])
        # năm trong tên phải giao với [span_lo, span_hi] (nới 1 năm)
        if not (lo - 1 <= span_hi and span_lo <= hi + 1):
            errs.append(f"TÊN-vs-YEAR lệch(tên {nyears}, year {y}, range {ds}..{de})")
    if ds is not None and de is not None and ds > de:
        errs.append(f"date range đảo({ds}>{de})")
    if y is not None and ds is not None and de is not None and not (ds - 1 <= y <= de + 1):
        errs.append(f"year ngoài range({y} ∉ {ds}..{de})")
    if y is not None and facts:
        fy = years_in(" ".join(facts))
        if fy and all(abs(v - y) > 1 for v in fy) and len(fy) >= 2:
            errs.append(f"facts KHÔNG nhắc year({y}; facts có {sorted(set(fy))[:4]})")

    # C) known exact
    ky = KNOWN_EXACT.get(fold(name))
    if ky is not None and y is not None and abs(y - ky) > 1:
        errs.append(f"YEAR-SAI-known(có {y}, chuẩn {ky})")

    # D) collision
    if fold(name) in COLLISION_STEMS:
        errs.append(f"COLLISION-thiếu-qualifier({fold(name)})")

    if errs:
        c["_errs"] = errs; flagged.append(c)
        for e in errs: reasons[e.split("(")[0].strip()] += 1
    else:
        gated.append(c)

byname = defaultdict(list)
for c in gated: byname[fold(c["name"])].append(c)
dups = {k: v for k, v in byname.items() if len(v) > 1}
cross_year = {k: sorted({x.get("year") for x in v}, key=lambda z: (z is None, z))
              for k, v in dups.items() if len({x.get("year") for x in v}) > 1}

json.dump(gated, open(f"{SP}/cards_gated.json", "w"), ensure_ascii=False, indent=1)
json.dump(flagged, open(f"{SP}/cards_flagged.json", "w"), ensure_ascii=False, indent=1)

print(f"=== GATE TẤT ĐỊNH: {len(cards)} thẻ raw (L4-L7, 15/34 chunk) ===")
print(f"  ĐẠT  : {len(gated)}")
print(f"  FLAG : {len(flagged)}   lý do: {dict(reasons.most_common())}")
print(f"\n  trùng tên: {len(dups)} cụm | trùng tên KHÁC NĂM: {len(cross_year)}")
for k, ys in list(cross_year.items())[:8]: print(f"    - {k}: {ys}")
print(f"\n  theo lớp:", dict(sorted(Counter(c['_grade'] for c in gated).items())))
print(f"  theo kind:", dict(Counter(c['kind'] for c in gated).most_common(8)))
print(f"  có year: {sum(1 for c in gated if c.get('year') is not None)}/{len(gated)} | có traps: {sum(1 for c in gated if c.get('traps'))}/{len(gated)} | có aliases: {sum(1 for c in gated if c.get('aliases'))}/{len(gated)}")
print("\n  -- FLAG chi tiết --")
for c in flagged[:12]:
    print(f"    L{c['_grade']} {c['name'][:44]:<46} {c['_errs']}")
