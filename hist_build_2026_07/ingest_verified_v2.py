# -*- coding: utf-8 -*-
"""Nạp thẻ ĐÃ VERIFY (L4-L12) vào :HistEvent — bản v2 có GỘP THỰC THỂ tất định.

VÌ SAO CẦN v2: một sự kiện được dạy lại ở nhiều lớp -> nhiều thẻ cùng tên nhưng
NĂM MỎ NEO khác nhau (Lam Sơn 1418 vs 1427). Bản v1 thấy "khác năm" là thêm định
ngữ năm -> tạo 2 node anh-em -> query_hist_event() bắn SIBLING GUARD và HỎI LẠI
(hoặc len(top)!=1 -> nhường tầng dưới). Tức là nạp thô L4-L7 sẽ LÀM TỤT 608 thẻ
đang chạy. v2 gộp các thẻ CÙNG MỘT THỰC THỂ theo luật tất định dưới đây.

LUẬT GỘP (chỉ dùng dữ liệu trong thẻ, không LLM):
  M0 mọi thẻ cùng year (kể cả cùng None)            -> gộp
  M1 chỉ có <=1 năm xác định, phần còn lại None      -> gộp, lấy năm đó
  M2 TÊN chứa dải năm (vd '1418 - 1427') và mọi năm
     của thẻ nằm trong dải                           -> gộp, lấy năm nhỏ nhất
  M3 max(year) - min(year) <= 2 (lệch mốc chép sử)   -> gộp, lấy năm nhỏ nhất
  M4 mọi thẻ có kind thuộc {concept, period, movement}
     (khái niệm/giai đoạn: năm chỉ là mốc tương đối) -> gộp, lấy năm nhỏ nhất
  M5 KHOẢNG THỜI GIAN (date_start..date_end) của mọi thẻ GIAO NHAU
     (vd 'Loạn 12 sứ quân' 944-968 vs 965-968: cùng một thời kì, chỉ khác quy
      ước mốc mở đầu) -> gộp, giữ năm của thẻ nền (nhiều facts nhất).
     Hai sự kiện KHÁC nhau thật (ĐBP 1954 vs ĐBP trên không 1972) không giao.
  còn lại = KHÁC THỰC THỂ THẬT -> giữ riêng + thêm định ngữ năm (như v1)

KHOÁ MERGE = (name_norm của tên hiển thị, year) — ổn định qua các lần chạy lại.
Node bị v1 tạo ra nhưng v2 không còn sinh nữa = THỪA -> liệt kê, backup, xoá.
Reversible: ingest_batch + backup toàn bộ property ra JSON.
Creds qua env EDU_NEO4J_PASS. Chạy `--dry` để chỉ xem quyết định, không ghi DB."""
import json, os, re, sys, unicodedata
from collections import defaultdict, Counter

BATCH = "histevent_v3_2026_09_05"
PREV_BATCHES = ("histevent_verified_2026_08_02", "histevent_v1_2026_07_26", "histevent_v2_2026_07_27")
HERE = os.path.dirname(os.path.abspath(__file__))
DRY = "--dry" in sys.argv

STOP_ALIAS = {"un", "eu", "mi", "my", "ta", "ho", "le", "ly", "tu", "vn", "usa", "anh", "phap",
              "duc", "nga", "mo", "co", "cu", "ba", "nam", "bac", "trung", "dong", "tay", "vua", "dang"}
SOAN = ("loigiaihay", "vietjack", "vndoc", "tech12h", "hoc247", "hoidap", "lazi", "tailieu")
GOOD = ("wikipedia", "wikidata", "nguoikesu", ".gov.vn", "baotang", "britannica", "history.com",
        "dangcongsan", "nhandan")
SOFT_KINDS = {"concept", "period", "movement"}


def fold(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").replace("đ", "d")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s)).strip()


def years_in(text):
    out = []
    for m in re.finditer(r"(\d{3,4})\s*(TCN|tcn|trước Công nguyên|trước công nguyên)?", text or ""):
        y = int(m.group(1))
        if m.group(2):
            y = -y
        if -3000 <= y <= 2030:
            out.append(y)
    return out


def tier_of(c):
    ss = [s.lower() for s in (c.get("sources") or []) if isinstance(s, str)]
    if any(any(k in s for k in GOOD) for s in ss):
        return "web_verified"
    if any(any(k in s for k in SOAN) for s in ss):
        return "soanbai_verified"
    return "unknown_verified"


def _span(c):
    """Khoảng [lo,hi] của thẻ, ưu tiên date_start/date_end, lùi về year."""
    def dy(d):
        if not isinstance(d, str):
            return None
        neg = bool(re.search(r"tcn|trước công nguyên|bc", d, re.I)) or d.strip().startswith("-")
        m = re.search(r"\b(\d{4})\b", d) or re.search(r"\b(\d{1,4})\b", d)
        if not m:
            return None
        return -int(m.group(1)) if neg else int(m.group(1))
    lo, hi = dy(c.get("date_start")), dy(c.get("date_end"))
    y = c.get("year")
    vals = [v for v in (lo, hi, y) if v is not None]
    return (min(vals), max(vals)) if vals else None


def merge_rule(group):
    """Trả (rule, year_chung) nếu CÙNG THỰC THỂ; (None, None) nếu khác thực thể."""
    ys_all = [c.get("year") for c in group]
    ys = sorted({y for y in ys_all if y is not None})
    if len(set(ys_all)) == 1:
        return "M0", ys_all[0]
    if len(ys) <= 1:
        return "M1", (ys[0] if ys else None)
    nm_years = years_in(group[0]["name"])
    if len(nm_years) >= 2 and all(min(nm_years) <= y <= max(nm_years) for y in ys):
        return "M2", min(ys)
    if ys[-1] - ys[0] <= 2:
        return "M3", ys[0]
    if all((c.get("kind") or "event") in SOFT_KINDS for c in group):
        return "M4", ys[0]
    sp = [_span(c) for c in group]
    if all(s is not None for s in sp) and max(s[0] for s in sp) <= min(s[1] for s in sp):
        return "M5", "BASE"
    return None, None


def fuse(group, year):
    """Gộp nhóm thành 1 thẻ: nền = thẻ nhiều facts nhất; hợp nhất facts/traps/alias/nguồn/lớp."""
    base = dict(max(group, key=lambda c: (len(c.get("facts") or []), len(c.get("summary") or ""))))
    seen, facts = set(), []
    for c in sorted(group, key=lambda c: -len(c.get("facts") or [])):
        for f in (c.get("facts") or []):
            k = fold(f)[:80]
            if k and k not in seen:
                seen.add(k)
                facts.append(f)
    base["facts"] = facts[:14]
    tr, seen_t = [], set()
    for c in group:
        for t in (c.get("traps") or []):
            k = fold(t)[:80]
            if k and k not in seen_t:
                seen_t.add(k)
                tr.append(t)
    base["traps"] = tr[:8]
    al = set()
    for c in group:
        al |= set(c.get("aliases") or [])
        al.add(c["name"])
    base["aliases"] = sorted(al)
    src, seen_s = [], set()
    for c in group:
        for s in (c.get("sources") or []):
            if s not in seen_s:
                seen_s.add(s)
                src.append(s)
    base["sources"] = src[:8]
    grades = sorted({c.get("_grade") or c.get("grade") for c in group if (c.get("_grade") or c.get("grade"))})
    base["_grades"] = grades
    base["_grade"] = grades[0] if grades else base.get("_grade")
    base["year"] = base.get("year") if year == "BASE" else year
    return base


# ── 1. đọc thẻ đã qua gate ──
cards = json.load(open(f"{HERE}/cards_v_gated.json", encoding="utf-8"))
print(f"vào: {len(cards)} thẻ verified + qua gate  |  theo lớp: "
      f"{dict(sorted(Counter(c.get('_grade') for c in cards).items()))}")

by = defaultdict(list)
for c in cards:
    by[fold(c["name"])].append(c)

final, stat = [], Counter()
split_report = []
for nn, group in by.items():
    if len(group) == 1:
        final.append(group[0])
        stat["đơn"] += 1
        continue
    rule, y = merge_rule(group)
    if rule:
        final.append(fuse(group, y))
        stat[f"gộp {rule}"] += 1
        stat["thẻ bị gộp mất"] += len(group) - 1
    else:
        ys = sorted({c.get("year") for c in group}, key=lambda z: (z is None, z))
        split_report.append((nn, ys))
        for c in group:
            yv = c.get("year")
            if yv is not None and str(yv) not in c["name"]:
                c["aliases"] = sorted(set((c.get("aliases") or []) + [c["name"]]))
                c["name"] = f"{c['name']} ({yv})"
            final.append(c)
        stat["TÁCH (khác thực thể)"] += 1

print("  " + " | ".join(f"{k}={v}" for k, v in sorted(stat.items())))
print(f"  -> còn {len(final)} thực thể")
if split_report:
    print("  TÁCH riêng (khác thực thể thật):")
    for nn, ys in split_report:
        print(f"    - {nn[:50]:<52} {ys}")

# ── 2. đối chiếu với DB (dry) hoặc ghi DB ──
want = {}
for c in final:
    nn = fold(c["name"])
    if not nn:
        continue
    want[(nn, c.get("year") if c.get("year") is not None else -99999)] = c
print(f"  khoá (name_norm, year) duy nhất: {len(want)}")

probe = f"{HERE}/hist_probe_keys.json"
if DRY and os.path.exists(probe):
    have = json.load(open(probe, encoding="utf-8"))
    hk = {(h["n"], h["y"] if h["y"] is not None else -99999): h for h in have}
    new = [k for k in want if k not in hk]
    upd = [k for k in want if k in hk]
    want_norms = {k[0] for k in want}
    def _base_norm(cn):
        return fold(re.sub(r"(\s*\(-?\d+\))+$", "", cn or ""))
    left = [h for k, h in hk.items() if k not in want and h.get("v") is True]
    gold_keys = {(h["n"], h["y"] if h["y"] is not None else -99999) for h in have if h.get("t") == "gold"}
    gold_upd = [k for k in upd if k in gold_keys]
    stale = [h for h in left if h.get("t") != "gold"
             and (h["n"] in want_norms or _base_norm(h.get("cn")) in want_norms)]
    keep_gold = [h for h in left if h.get("t") == "gold"]
    keep_other = [h for h in left if h.get("t") != "gold" and h not in stale]
    print(f"\n=== ĐỐI CHIẾU DB ({len(have)} node hiện có) ===")
    print(f"  TẠO MỚI : {len(new)}")
    print(f"  CẬP NHẬT: {len(upd)}  (trong đó ĐÈ LÊN THẺ GOLD: {len(gold_upd)} -> sẽ được bảo vệ)")
    print(f"  XOÁ (bản cũ của chính thực thể v2 ghi lại): {len(stale)}")
    for h in stale[:45]:
        print(f"    - L{h.get('g')} {str(h.get('cn'))[:54]:<56} year={h.get('y')} tier={h.get('t')}")
    print(f"  GIỮ NGUYÊN: gold={len(keep_gold)} | thẻ khác không liên quan={len(keep_other)}")
    for h in keep_other[:12]:
        print(f"    . L{h.get('g')} {str(h.get('cn'))[:54]:<56} year={h.get('y')} tier={h.get('t')}")
    json.dump({"new": len(new), "upd": len(upd),
               "stale": [{"e": h["e"], "cn": h.get("cn"), "y": h.get("y"), "g": h.get("g")} for h in stale]},
              open(f"{HERE}/ingest_v2_dryrun.json", "w"), ensure_ascii=False, indent=1)
    print("  -> ingest_v2_dryrun.json")
    sys.exit(0)

if DRY:
    sys.exit("DRY: thiếu hist_probe_keys.json để đối chiếu")

from neo4j import GraphDatabase  # noqa: E402
PASS = os.getenv("EDU_NEO4J_PASS")
if not PASS:
    sys.exit("Thiếu EDU_NEO4J_PASS")
drv = GraphDatabase.driver(os.getenv("EDU_NEO4J_URI", "bolt://localhost:7688"),
                           auth=(os.getenv("EDU_NEO4J_USER", "neo4j"), PASS))

created, touched, alias_n, gold_kept = [], [], 0, 0
with drv.session() as s:
    gold_keys = {(r["n"], r["y"] if r["y"] is not None else -99999): r["e"] for r in s.run(
        "MATCH (h:HistEvent) WHERE h.source_tier='gold' "
        "RETURN elementId(h) AS e, h.name_norm AS n, h.year AS y").data()}
    print(f"  thẻ GOLD được bảo vệ: {len(gold_keys)}")
    for (nn, ykey), c in want.items():
        # THẺ GOLD (chép từ ghi chú của người dùng) = nguồn tin cậy nhất:
        # chỉ bồi thêm alias/grades, KHÔNG ghi đè facts/summary/tier.
        if (nn, ykey) in gold_keys:
            eid = gold_keys[(nn, ykey)]
            touched.append(eid)
            gold_kept += 1
            s.run("""MATCH (h) WHERE elementId(h)=$e
                     SET h.grades=coalesce(h.grades,[])+[x IN $gs WHERE NOT x IN coalesce(h.grades,[])]""",
                  e=eid, gs=c.get("_grades") or [])
            for a in {nn} | {fold(x) for x in (c.get("aliases") or [])}:
                if not a or len(a) < 4 or a in STOP_ALIAS:
                    continue
                s.run("""MERGE (al:HistAlias {value_norm:$a})
                         ON CREATE SET al.ingest_batch=$b
                         WITH al MATCH (h) WHERE elementId(h)=$e
                         MERGE (al)-[:ALIAS_OF]->(h)""", a=a, e=eid, b=BATCH)
                alias_n += 1
            continue
        r = s.run("""
            MERGE (h:HistEvent {name_norm:$nn, year:$ykey})
            ON CREATE SET h._new=true
            SET h.canonical_name=$name, h.kind=$kind, h.date_start=$ds, h.date_end=$de,
                h.place=$place, h.actors=$actors, h.summary=$summary, h.facts=$facts,
                h.traps=$traps, h.topic_title=$topic, h.grade=$g, h.grades=$gs,
                h.sources=$sources, h.subject_code='lich_su', h.verified=true,
                h.ingest_batch=$batch, h.fixed_notes=$fixed,
                h.source_tier=$tier
            RETURN elementId(h) AS e, coalesce(h._new,false) AS isnew
        """, nn=nn, ykey=ykey, name=c["name"], kind=c.get("kind", "event"),
             ds=c.get("date_start"), de=c.get("date_end"), place=c.get("place"),
             actors=c.get("actors") or [], summary=c.get("summary", ""),
             facts=c.get("facts") or [], traps=c.get("traps") or [],
             topic=c.get("topic_title", ""), g=c.get("_grade") or c.get("grade"),
             gs=c.get("_grades") or [], sources=c.get("sources") or [],
             tier=tier_of(c), batch=BATCH, fixed=c.get("fixed") or []).single()
        eid = r["e"]
        touched.append(eid)
        if r["isnew"]:
            created.append(eid)
        s.run("MATCH (h) WHERE elementId(h)=$e REMOVE h._new", e=eid)
        for a in {nn} | {fold(x) for x in (c.get("aliases") or [])}:
            if not a or len(a) < 4 or a in STOP_ALIAS:
                continue
            s.run("""MERGE (al:HistAlias {value_norm:$a})
                     ON CREATE SET al.ingest_batch=$b
                     WITH al MATCH (h) WHERE elementId(h)=$e
                     MERGE (al)-[:ALIAS_OF]->(h)""", a=a, e=eid, b=BATCH)
            alias_n += 1
    print(f"TẠO MỚI {len(created)} | CHẠM {len(touched)} | alias-link {alias_n} | GOLD giữ nguyên {gold_kept}")

    # ── 3. dọn node THỪA — CỔNG HẸP ──
    # Chỉ xoá node là BẢN CŨ CỦA CHÍNH THỰC THỂ v2 vừa ghi: cùng name_norm (sau khi
    # bóc định ngữ năm ' (1954)' mà v1 tự thêm) nhưng khác year. Node GOLD và node
    # không liên quan (thẻ v1 khác, chưa verify lại) TUYỆT ĐỐI không đụng tới.
    cand = s.run("""MATCH (h:HistEvent)
                    WHERE h.verified=true AND NOT elementId(h) IN $keep
                      AND coalesce(h.source_tier,'') <> 'gold'
                    RETURN elementId(h) AS e, h.canonical_name AS cn, h.name_norm AS nn,
                           h.year AS y, h.grade AS g, h.source_tier AS t,
                           properties(h) AS p""", keep=touched).data()
    want_norms = {k[0] for k in want}
    def _base_norm(cn):
        b = re.sub(r"(\s*\(-?\d+\))+$", "", cn or "")
        return fold(b)
    stale = [h for h in cand if h["nn"] in want_norms or _base_norm(h["cn"]) in want_norms]
    skipped = [h for h in cand if h not in stale]
    print(f"  không đụng tới: {len(skipped)} node (gold/thẻ khác)")
    print(f"\nTHỪA (bản cũ của chính thực thể v2 vừa ghi): {len(stale)}/{len(cand)} ứng viên")
    for h in stale[:25]:
        print(f"  - L{h['g']} {str(h['cn'])[:56]:<58} year={h['y']}")
    json.dump(stale, open(f"{HERE}/ingest_v2_stale_backup.json", "w"), ensure_ascii=False, indent=1)
    if stale:
        n = s.run("MATCH (h:HistEvent) WHERE elementId(h) IN $ids DETACH DELETE h RETURN count(*) AS c",
                  ids=[h["e"] for h in stale]).single()["c"]
        print(f"  -> đã xoá {n} (backup ingest_v2_stale_backup.json)")
    orph = s.run("MATCH (a:HistAlias) WHERE NOT (a)-[:ALIAS_OF]->() DETACH DELETE a RETURN count(*) AS c").single()["c"]
    print(f"  -> xoá {orph} alias mồ côi")

json.dump({"batch": BATCH, "created": created, "touched": touched},
          open(f"{HERE}/ingest_v2_backup.json", "w"))

with drv.session() as s:
    print("\n=== SAU KHI NẠP ===")
    print("  HistEvent:", s.run("MATCH (h:HistEvent) RETURN count(*) AS c").single()["c"],
          "| verified:", s.run("MATCH (h:HistEvent {verified:true}) RETURN count(*) AS c").single()["c"])
    rows = s.run("MATCH (h:HistEvent {verified:true}) RETURN h.grade AS g, count(*) AS c ORDER BY g").data()
    print("  theo lớp:", "  ".join(f"L{r['g']}:{r['c']}" for r in rows))
    print("  HistAlias:", s.run("MATCH (a:HistAlias) RETURN count(*) AS c").single()["c"])
    print(f"  Rollback thẻ mới: MATCH (n:HistEvent) WHERE elementId(n) IN <ingest_v2_backup.created> DETACH DELETE n")
