# -*- coding: utf-8 -*-
"""READ-ONLY audit kho recite (LiteratureText/:7688). Xuất list chỗ cần sửa: typo / metadata-in-body / footnote / dup-title. KHÔNG ghi Neo4j."""
import unicodedata, re, json
from collections import Counter, defaultdict
from neo4j import GraphDatabase

# ── validator âm tiết (tái dùng vn_typo2) ──
TONE = {0x0300, 0x0301, 0x0303, 0x0309, 0x0323}
def detone(w):
    o = unicodedata.normalize("NFD", w); o = "".join(c for c in o if ord(c) not in TONE)
    return unicodedata.normalize("NFC", o).lower()
ONSETS = ['ngh','ng','nh','ch','gh','gi','kh','ph','th','tr','qu','b','c','d','đ','g','h','k','l','m','n','p','q','r','s','t','v','x','']
R = """a ac ach ai am an ang anh ao ap at au ay ăc ăm ăn ăng ăp ăt âc âm ân âng âp ât âu ây
e ec em en eng eo ep et ê êch êm ên ênh êp êt êu i ich im in inh ip it iu ia iêc iêm iên iêng iêp iêt iêu
o oc oe oen oeo oet oi om on ong oong op ot oo oa oac oach oai oam oan oang oanh oao oap oat oay oăc oăm oăn oăng oăt oăp
ô ôc ôi ôm ôn ông ôp ôt ơ ơi ơm ơn ơp ơt u uc ui um un ung up ut ua uô uôc uôi uôm uôn uông uôt uơ
uy uya uych uyên uyêt uynh uyt uê uêch uên uênh uân uâng uât uây uâ
ư ưc ưi ưng ưt ưu ưa ươ ươc ươi ươm ươn ương ươp ươt ươu yê yêm yên yêng yêt yêu ynh
y uyu uych ooc oong quơ khuya"""
RHYMES = set(R.split())
VALID = set(o + r for o in ONSETS for r in RHYMES)
def okword(tok):
    d = detone(tok)
    if d in VALID: return True
    for o in ONSETS:
        if o and d.startswith(o) and d[len(o):] in RHYMES: return True
    return False
CH = "a-zA-ZàáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđĐ"
WORDRE = re.compile(f"[{CH}]+")

# ── detectors metadata / footnote ──
META = re.compile(r'(nhà xuất bản|nxb\b|tuyển tập|ngữ văn\s*\d|tr\.?\s*\d{1,4}\b|trang\s+\d+|\bin trong\b|\btheo\b.*\d{4}|\(\s*(?:19|20)\d\d\s*\)|,\s*(?:19|20)\d\d\s*$)', re.I)
YEAR = re.compile(r'\b(?:19|20)\d\d\b')
FOOT = re.compile(r'\(\s*\d{1,3}\s*\)|\[\s*\d{1,3}\s*\]')
HTML = re.compile(r'<[^>\n]{1,40}>|https?://|www\.|\b(?:img|src|href|div|span|px|jpg|png)\b|\.(?:com|vn|org|html|net)\b', re.I)
def has_dia(tok):  # token mang dấu tiếng Việt -> khả năng cao là typo thật (khác foreign/abbrev ascii)
    return any(ch not in "abcdefghijklmnopqrstuvwxyz" for ch in tok.lower())

drv = GraphDatabase.driver("bolt://localhost:7688", auth=("neo4j", __import__("os").environ.get("NEO4J_PW","")))
with drv.session() as s:
    rows = s.run("""MATCH (lt:LiteratureText) WHERE lt.full_text IS NOT NULL
        RETURN toString(coalesce(lt.grade,'?')) AS g, coalesce(lt.work_name,lt.title,'?') AS w,
               lt.work_name_norm AS wn, coalesce(lt.series,'') AS ser, coalesce(lt.author,'') AS au,
               lt.full_text AS t, coalesce(lt.uid,'') AS uid, id(lt) AS nid""").data()
drv.close()
print(f"Quét {len(rows)} node LiteratureText.\n")

typo_dia = Counter(); typo_ascii = Counter(); typo_nodes = []
meta_nodes = []; foot_nodes = []; author_leak = []; html_nodes = []
by_norm = defaultdict(lambda: defaultdict(list))   # wn -> grade -> [work]

for r in rows:
    t = unicodedata.normalize("NFC", r["t"])       # FIX: NFC trước khi tách từ (kho lưu NFD)
    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    # #5 dup key
    if r["wn"]:
        by_norm[r["wn"]][r["g"]].append(r["w"])
    # #1 typo: token thường (không hoa=không phải tên riêng), >=2 ký tự
    bad_dia = []; bad_ascii = []
    for wd in WORDRE.findall(t):
        if len(wd) < 2 or wd[0].isupper(): continue
        wl = wd.lower()
        if okword(wl): continue
        (bad_dia if has_dia(wl) else bad_ascii).append(wl)
    if bad_dia or bad_ascii:
        typo_dia.update(bad_dia); typo_ascii.update(bad_ascii)
        typo_nodes.append((r["g"], r["w"], r["nid"], Counter(bad_dia), Counter(bad_ascii)))
    # HTML/URL leak
    if HTML.search(t):
        html_nodes.append((r["g"], r["w"], r["nid"], HTML.findall(t)[:5]))
    # #2 metadata-in-body
    hits = [ln for ln in lines if META.search(ln)]
    tail = lines[-3:]
    tail_year = [ln for ln in tail if YEAR.search(ln) and len(ln) < 60]
    if hits or tail_year:
        meta_nodes.append((r["g"], r["w"], r["nid"], (hits + [x for x in tail_year if x not in hits])[:4]))
    # #3 footnote (N)
    fh = FOOT.findall(t)
    if fh:
        foot_nodes.append((r["g"], r["w"], r["nid"], Counter(fh)))
    # author leak: tên tác giả xuất hiện như 1 dòng ở cuối
    au = r["au"].strip()
    if au and len(au) >= 3:
        for ln in tail:
            if detone(au) == detone(ln) or (detone(au) in detone(ln) and len(ln) < len(au) + 12):
                author_leak.append((r["g"], r["w"], r["nid"], ln)); break

# ── REPORT ──
out = {}
print("═"*68)
print("① TYPO CÓ DẤU — khả năng cao là lỗi thật (âm tiết sai, vd 'nhưn')")
print("═"*68)
topd = typo_dia.most_common(55)
print(f"  {len(typo_dia)} loại token có-dấu-sai. Top (số lần | token):")
for tok, n in topd:
    print(f"    {n:4d}×  {tok!r}")
print("\n  ①b ASCII/FOREIGN/ABBREV (đa phần phiên âm nước ngoài/viết tắt — soi kỹ, nhiều FP):")
for tok, n in typo_ascii.most_common(20):
    print(f"    {n:4d}×  {tok!r}")
out["typo_dia_tokens"] = topd
out["typo_ascii_tokens"] = typo_ascii.most_common(60)
out["typo_nodes"] = [{"g": g, "w": w, "nid": nid, "dia": dict(cd), "ascii": dict(ca)} for g, w, nid, cd, ca in typo_nodes]

print("\n" + "═"*68)
print("①c HTML/URL LEAK trong thân (img/src/https/<tag>/.com…) — cruft đọc-thành-tiếng")
print("═"*68)
print(f"  {len(html_nodes)} node:")
for g, w, nid, hits in html_nodes[:40]:
    print(f"    L{g:>3} {w[:34]:34s} | {hits}")
out["html_nodes"] = [{"g": g, "w": w, "nid": nid, "hits": hits} for g, w, nid, hits in html_nodes]

print("\n" + "═"*68)
print("② METADATA lẫn trong THÂN BÀI (NXB/năm/Ngữ văn/tr.NN/'in trong')")
print("═"*68)
print(f"  {len(meta_nodes)} node dính:")
for g, w, nid, snips in meta_nodes[:60]:
    print(f"    L{g:>3} {w[:34]:34s} | " + " ⟂ ".join(s[:46] for s in snips))
out["metadata_nodes"] = [{"g": g, "w": w, "nid": nid, "snips": snips} for g, w, nid, snips in meta_nodes]

print("\n" + "═"*68)
print("②b AUTHOR/năm rớt vào DÒNG CUỐI thân bài (vd Tây Tiến, Sóng)")
print("═"*68)
print(f"  {len(author_leak)} node:")
for g, w, nid, ln in author_leak[:50]:
    print(f"    L{g:>3} {w[:32]:32s} | dòng cuối = {ln[:40]!r}")
out["author_leak"] = [{"g": g, "w": w, "nid": nid, "last_line": ln} for g, w, nid, ln in author_leak]

print("\n" + "═"*68)
print("③ CHÚ THÍCH SỐ (N) nhúng trong thân")
print("═"*68)
print(f"  {len(foot_nodes)} node:")
for g, w, nid, c in foot_nodes[:50]:
    print(f"    L{g:>3} {w[:34]:34s} | {dict(c)}")
out["footnote_nodes"] = [{"g": g, "w": w, "nid": nid, "marks": dict(c)} for g, w, nid, c in foot_nodes]

print("\n" + "═"*68)
print("⑤ DUP TÍTLE trùng tên KHÁC KHỐI (cần tag phân biệt anchor)")
print("═"*68)
dups = {wn: dict(gm) for wn, gm in by_norm.items() if len({g for g in gm}) > 1}
print(f"  {len(dups)} tựa trùng qua nhiều lớp:")
for wn, gm in sorted(dups.items()):
    print(f"    {wn[:40]:40s} -> lớp {sorted(gm.keys())}")
out["dup_titles"] = dups

with open("/tmp/recite_audit.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
print("\n>> chi tiết đầy đủ: /tmp/recite_audit.json")
print(f">> TÓM: typo-node={len(typo_nodes)} html-leak={len(html_nodes)} metadata={len(meta_nodes)} author-leak={len(author_leak)} footnote={len(foot_nodes)} dup-title={len(dups)}")
