# -*- coding: utf-8 -*-
"""TEST THEO KIẾN THỨC TỪNG BÀI HỌC.
Input: verified_g*_c*.json (fact-card đã verify) + ls_items (khung bài).
Sinh câu hỏi TẤT ĐỊNH từ field thẻ (year/place/actors/person) -> hỏi RAG -> chấm context
-> báo cáo THEO TỪNG BÀI (format giống checklist user: mỗi bài ✓/~/✗ + câu sai).
Usage: perlesson_test.py <port> <tag> [grade_filter]
"""
import glob, json, re, sys, unicodedata
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

import requests

PORT = int(sys.argv[1]); TAG = sys.argv[2]
GFILTER = int(sys.argv[3]) if len(sys.argv) > 3 else None
CARD_DIR = "/tmp/histcards"

def fold(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").replace("đ", "d")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s)).strip()

YEAR_RE = re.compile(r"\b(1[0-9]{3}|20[0-2][0-9]|[1-9][0-9]{2})\b")

def gen_questions(card):
    """Sinh câu hỏi tất định từ field thẻ. Trả [(qtext, expect[], forbid[], qkind)]."""
    qs = []
    name = card["name"]
    year = card.get("year")
    traps_blob = " ".join(card.get("traps") or [])
    if year:
        # năm-bẫy = năm 4 chữ số xuất hiện trong traps khác năm đúng (±0)
        trap_years = [y for y in YEAR_RE.findall(traps_blob) if y != str(year)]
        qs.append((f"{name} diễn ra năm nào", [str(year)], trap_years[:3], "year"))
    place = card.get("place")
    if place and len(place) >= 3 and card.get("kind") != "person":
        # token địa danh chính (bỏ từ nối)
        ptoks = [t for t in re.split(r"[,–\-/]| và ", place) if len(t.strip()) >= 3]
        if ptoks:
            qs.append((f"{name} diễn ra ở đâu", [fold(t) for t in ptoks[:3]], [], "place"))
    actors = [a for a in (card.get("actors") or []) if len(a) >= 3]
    if actors and card.get("kind") in ("event", "campaign", "battle", "movement", "treaty"):
        qs.append((f"Ai lãnh đạo hoặc tham gia {name}", [fold(a) for a in actors[:4]], [], "actor"))
    if card.get("kind") == "person":
        # người: hỏi "là ai", chấm bằng token đặc trưng từ summary (danh từ riêng/năm)
        toks = [fold(t) for t in YEAR_RE.findall(card.get("summary", ""))][:2]
        key = toks or [fold(name.split()[-1])]
        qs.append((f"{name} là ai", key, [], "person"))
    return qs

# ---- load cards, gắn vào bài ----
cards = []
for f in sorted(glob.glob(f"{CARD_DIR}/verified_g*_c*.json")):
    try:
        d = json.load(open(f))
        for c in d.get("cards", []):
            c["_grade"] = d.get("grade")
            cards.append(c)
    except Exception as e:
        print(f"[warn] {f}: {e}")

tests = []  # (grade, topic_title, qtext, expect, forbid, qkind, card_name)
for c in cards:
    g = c.get("_grade")
    if GFILTER and g != GFILTER: continue
    for (q, exp, forb, kd) in gen_questions(c):
        tests.append({"g": g, "topic": c.get("topic_title", "?"), "q": q,
                      "expect": exp, "forbid": forb, "kind": kd, "card": c["name"]})

print(f"[gen] {len(cards)} thẻ -> {len(tests)} câu hỏi (port {PORT})")

def run_one(i_t):
    i, t = i_t
    try:
        d = requests.post(f"http://localhost:{PORT}/v2/rag/retrieve",
                          json={"query": t["q"], "session_id": f"pl_{TAG}_{i}"}, timeout=35).json()
    except Exception:
        return {**t, "res": "ERR"}
    c = fold((d.get("context") or ""))
    craw = (d.get("context") or "").lower()
    has_e = any(fold(e) in c or e.lower() in craw for e in t["expect"])
    has_f = any(f in craw or fold(f) in c for f in t["forbid"])
    miss = (not craw.strip()) or ("khong tim" in c)
    res = "PASS" if (has_e and not has_f) else ("TRAP" if has_f else ("MISS" if miss else "NOFACT"))
    return {**t, "res": res}

with ThreadPoolExecutor(max_workers=6) as ex:
    results = list(ex.map(run_one, enumerate(tests)))

json.dump(results, open(f"/tmp/perlesson_{TAG}.json", "w"), ensure_ascii=False)

# ---- báo cáo theo TỪNG BÀI (topic) ----
by_topic = defaultdict(list)
for r in results:
    by_topic[(r["g"], r["topic"])].append(r)

print(f"\n=== BÁO CÁO THEO TỪNG BÀI — {TAG} ===")
tot_p = tot_q = 0
grade_stat = defaultdict(lambda: [0, 0])
lines = []
for (g, topic), rs in sorted(by_topic.items()):
    p = sum(1 for r in rs if r["res"] == "PASS"); n = len(rs)
    tot_p += p; tot_q += n
    grade_stat[g][0] += p; grade_stat[g][1] += n
    mark = "✓" if p == n else ("~" if p > 0 else "✗")
    fails = "; ".join(f"{r['kind']}:{r['res']}" for r in rs if r["res"] != "PASS")[:60]
    lines.append(f" {mark} L{g:<2} {topic[:46]:<48} {p}/{n}" + (f"  [{fails}]" if fails else ""))
for ln in lines: print(ln)
print(f"\n=== THEO LỚP ===")
for g in sorted(grade_stat):
    p, n = grade_stat[g]
    print(f"  L{g:<3} {p}/{n} = {100*p//max(n,1)}%")
print(f"  TỔNG {tot_p}/{tot_q} = {100*tot_p//max(tot_q,1)}%")
from collections import Counter
print("  verdict:", dict(Counter(r["res"] for r in results)))
