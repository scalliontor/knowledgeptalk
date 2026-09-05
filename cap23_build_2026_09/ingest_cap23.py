# -*- coding: utf-8 -*-
"""Nạp dữ liệu bù Tiếng Việt/Ngữ văn vào Neo4j — theo ĐÚNG khuôn các đợt trước.

Khuôn đã chạy được (đối chiếu VAN_RECITE_TH_2026_07 / VAN_THEORY_TH_2026_07):
  RECITE    (:Lesson)-[:HAS_RECITE]->(:LiteratureText {full_text, title:"Văn bản X"})
  COMPANION (:Lesson)-[:HAS_THEORY]->(:KnowledgeChunk {content_type:'theory', text, guiding_questions})
KnowledgeChunk đợt này KHÔNG cần embedding (đợt trước cũng 0/265) — truy hồi đi
đường neo `work_name_norm`, không đi vector.

⚠️ CỔNG NORM (bài học en-dash 05/09): `work_name_norm` phải bằng ĐÚNG `_fold` của prod
(giữ nguyên dấu câu, chỉ đổi '–'->'-'). Sai một ly là bài không bao giờ được tìm thấy.
Script tự kiểm và DỪNG nếu lệch.

Reversible: ingest_actor + ingest_batch + backup elementId.
  python3 ingest_cap1.py [thư_mục] [--dry]"""
import json, os, re, sys, unicodedata
from collections import Counter

HERE = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith("-") \
    else os.path.dirname(os.path.abspath(__file__))
DRY = "--dry" in sys.argv
TAG = os.path.basename(HERE).split("_")[0]                 # cap1 / cap23
ACTOR = f"VAN_{TAG.upper()}_2026_09_05"
BATCH = f"van_{TAG}_2026_09_05"
SERIES = {"KNTT": "KNTT", "CTST": "CTST", "CD": "CD", "Cánh Diều": "CD",
          "Kết nối tri thức": "KNTT", "Chân trời sáng tạo": "CTST"}


def _fold(s):
    """BẢN SAO NGUYÊN VĂN _fold() của prod — không được sửa."""
    s = (s or "").replace("đ", "d").replace("Đ", "D").replace("–", "-")
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


items = json.load(open(f"{HERE}/{TAG}_gated.json", encoding="utf-8"))
items = [i for i in items if (i.get("kind") or "").lower() in ("recite", "companion")]
print(f"vào: {len(items)} bài đã qua cổng  {dict(Counter(i['kind'] for i in items))}")

rows, bad = [], []
for it in items:
    wn = (it.get("ten_bai") or "").strip()
    wnn = _fold(wn).strip()
    g = it.get("grade")
    if not wnn or len(wnn) < 3 or "–" in wnn or _fold(wn).strip() != wnn:
        bad.append((wn, "norm không hợp lệ")); continue
    if not isinstance(g, int):
        bad.append((wn, f"lớp không hợp lệ ({g!r})")); continue
    rows.append({
        "kind": it["kind"], "wn": wn, "wnn": wnn, "g": g,
        "author": (it.get("tac_gia") or "").strip() or None,
        "series": SERIES.get((it.get("bo_sach") or "").strip()),
        "full_text": (it.get("full_text") or "").strip(),
        "comp": it.get("companion") or {},
        "url": next((u for u in (it.get("sources") or []) if isinstance(u, str)), None),
        "sources": [u for u in (it.get("sources") or []) if isinstance(u, str)][:4],
    })
if bad:
    print(f"  BỎ QUA {len(bad)}:", bad[:5])

# chống trùng norm trong chính lô
seen = Counter(r["wnn"] + f"|{r['g']}" for r in rows)
dup = [k for k, v in seen.items() if v > 1]
if dup:
    print(f"  ⚠ trùng trong lô: {len(dup)} -> giữ bản đầu")
    keep, out = set(), []
    for r in rows:
        k = r["wnn"] + f"|{r['g']}"
        if k in keep: continue
        keep.add(k); out.append(r)
    rows = out
print(f"  sẽ nạp: {len(rows)}  {dict(Counter(r['kind'] for r in rows))}  lớp={dict(sorted(Counter(r['g'] for r in rows).items()))}")


def comp_text(r):
    c = r["comp"]
    p = [f"Bài: {r['wn']}"]
    if r["author"]: p.append(f"Tác giả: {r['author']}")
    if c.get("tom_tat"): p.append(f"Tóm tắt: {c['tom_tat']}")
    if c.get("nhan_vat"): p.append(f"Nhân vật: {c['nhan_vat']}")
    if c.get("y_nghia"): p.append(f"Ý nghĩa: {c['y_nghia']}")
    return "\n".join(p)


if DRY:
    for r in rows[:6]:
        print(f"\n  [{r['kind']}] L{r['g']} {r['wn']}")
        print(f"     norm   : {r['wnn']}")
        print(f"     lesson : van{TAG}:{r['g']}:{r['wnn']}")
        print(f"     nội dung: {(r['full_text'] or comp_text(r))[:110]!r}")
    sys.exit(0)

from neo4j import GraphDatabase  # noqa: E402
drv = GraphDatabase.driver(os.getenv("EDU_NEO4J_URI", "bolt://localhost:7688"),
                           auth=(os.getenv("EDU_NEO4J_USER", "neo4j"), os.environ["EDU_NEO4J_PASS"]))
created = {"Lesson": [], "LiteratureText": [], "KnowledgeChunk": []}
skipped = []
with drv.session() as s:
    for r in rows:
        # đã có bài cùng norm + cùng lớp -> KHÔNG tạo trùng
        ex = s.run("""MATCH (n) WHERE n.work_name_norm=$wnn
                        AND (n:LiteratureText OR n:Lesson)
                        AND toString(n.grade)=toString($g)
                      RETURN count(*) AS c""", wnn=r["wnn"], g=r["g"]).single()["c"]
        if ex:
            skipped.append((r["wn"], r["g"])); continue

        lid = f"van{TAG}:{r['g']}:{r['wnn']}"
        le = s.run("""MERGE (l:Lesson {lesson_id:$lid})
                      ON CREATE SET l._new=true
                      SET l.subject_code='ngu_van', l.work_name=$wn, l.work_name_norm=$wnn,
                          l.grade=$g, l.title=$wn, l.ingest_actor=$actor, l.ingest_batch=$batch
                      RETURN elementId(l) AS e, coalesce(l._new,false) AS isnew""",
                   lid=lid, wn=r["wn"], wnn=r["wnn"], g=r["g"], actor=ACTOR, batch=BATCH).single()
        s.run("MATCH (l) WHERE elementId(l)=$e REMOVE l._new", e=le["e"])
        if le["isnew"]: created["Lesson"].append(le["e"])

        if r["kind"] == "recite":
            uid = f"van{TAG}rec:{r['g']}:{r['wnn']}"
            n = s.run("""MERGE (t:LiteratureText {uid:$uid})
                         ON CREATE SET t._new=true
                         SET t.subject_code='ngu_van', t.work_name=$wn, t.work_name_norm=$wnn,
                             t.grade=$g, t.title=$title, t.full_text=$ft, t.author=$au,
                             t.url=$url, t.series=$series, t.books=[],
                             t.ingest_actor=$actor, t.ingest_batch=$batch, t.sources=$srcs
                         RETURN elementId(t) AS e, coalesce(t._new,false) AS isnew""",
                      uid=uid, wn=r["wn"], wnn=r["wnn"], g=r["g"], title=f"Văn bản {r['wn']}",
                      ft=r["full_text"], au=r["author"], url=r["url"], series=r["series"],
                      actor=ACTOR, batch=BATCH, srcs=r["sources"]).single()
            s.run("MATCH (t) WHERE elementId(t)=$e REMOVE t._new", e=n["e"])
            if n["isnew"]: created["LiteratureText"].append(n["e"])
            s.run("""MATCH (l) WHERE elementId(l)=$le MATCH (t) WHERE elementId(t)=$te
                     MERGE (l)-[rel:HAS_RECITE]->(t) ON CREATE SET rel.batch=$b""",
                  le=le["e"], te=n["e"], b=BATCH)
        else:
            uid = f"van{TAG}_kc:{r['g']}:{r['wnn']}"
            n = s.run("""MERGE (k:KnowledgeChunk {uid:$uid})
                         ON CREATE SET k._new=true
                         SET k.subject_code='ngu_van', k.content_type='theory',
                             k.work_name=$wn, k.work_name_norm=$wnn, k.grade=$g,
                             k.text=$text, k.guiding_questions=$gq,
                             k.ingest_actor=$actor, k.ingest_batch=$batch, k.sources=$srcs
                         RETURN elementId(k) AS e, coalesce(k._new,false) AS isnew""",
                      uid=uid, wn=r["wn"], wnn=r["wnn"], g=r["g"], text=comp_text(r),
                      gq=json.dumps([q for q in (r["comp"].get("cau_hoi") or []) if q], ensure_ascii=False),
                      actor=ACTOR, batch=BATCH, srcs=r["sources"]).single()
            s.run("MATCH (k) WHERE elementId(k)=$e REMOVE k._new", e=n["e"])
            if n["isnew"]: created["KnowledgeChunk"].append(n["e"])
            s.run("""MATCH (l) WHERE elementId(l)=$le MATCH (k) WHERE elementId(k)=$ke
                     MERGE (l)-[rel:HAS_THEORY]->(k) ON CREATE SET rel.batch=$b""",
                  le=le["e"], ke=n["e"], b=BATCH)

json.dump({"actor": ACTOR, "batch": BATCH, "created": created, "skipped": skipped},
          open(f"{HERE}/ingest_{TAG}_backup.json", "w"), ensure_ascii=False, indent=1)
print(f"\nTẠO MỚI  Lesson={len(created['Lesson'])} LiteratureText={len(created['LiteratureText'])} KnowledgeChunk={len(created['KnowledgeChunk'])}")
print(f"BỎ (đã có bài cùng tên+lớp): {len(skipped)}", skipped[:6])
print(f"Rollback: MATCH (n) WHERE n.ingest_batch='{BATCH}' DETACH DELETE n")

with drv.session() as s:
    print("\n=== kiểm tra lại 5 bài vừa nạp ===")
    for r in s.run("""MATCH (l:Lesson {ingest_batch:$b})
                      OPTIONAL MATCH (l)-[:HAS_RECITE]->(t:LiteratureText)
                      OPTIONAL MATCH (l)-[:HAS_THEORY]->(k:KnowledgeChunk)
                      RETURN l.work_name AS w, l.work_name_norm AS wn, l.grade AS g,
                             t.title AS rt, size(coalesce(t.full_text,'')) AS flen,
                             size(coalesce(k.text,'')) AS klen LIMIT 5""", b=BATCH):
        print(f"   L{r['g']} {str(r['w'])[:34]:<36} norm={str(r['wn'])[:34]:<36} recite={r['flen']} giảng={r['klen']}")
