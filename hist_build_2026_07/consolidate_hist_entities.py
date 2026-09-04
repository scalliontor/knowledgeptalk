# -*- coding: utf-8 -*-
"""HỢP NHẤT các :HistEvent là CÙNG MỘT THỰC THỂ nhưng bị tách node vì biến thể tên.

VÌ SAO: name_norm giữ nguyên ngoặc/nháy/tiền tố nên cùng một sự kiện thành nhiều node:
    'Chiến dịch Điện Biên Phủ'                (gold, 5 facts)
    'Chiến dịch Điện Biên Phủ (1954)'         (14 facts)
    'Chiến dịch Điện Biên Phủ (13/3 - 7/5/1954)'
    'Kế hoạch Na-va' vs 'Kế hoạch Nava'       (khác cách phiên âm)
Alias trỏ vào nhiều node -> tầng T2 gộp-trùng chọn bản NHIỀU FACTS NHẤT, có thể bỏ
qua bản GOLD chứa đúng dữ kiện cần -> battery ra NOFACT; hoặc len(top)>1 -> AMBIG.

KHOÁ THỰC THỂ (tất định):
  bỏ mọi cụm trong ngoặc -> bỏ nháy/ngoặc kép -> bỏ TIỀN TỐ loại chung
  ('chiến dịch/chiến thắng/cuộc/phong trào/khởi nghĩa/...') -> bỏ đệm 'xâm lược'
  -> fold bỏ dấu -> BỎ HẾT KHOẢNG TRẮNG  ('na va' == 'nava', 'véc xai' == 'vécxai')

CHỈ gộp khi TRÙNG KHOÁ **VÀ** TRÙNG `kind` **VÀ** TRÙNG NĂM (hoặc bên kia không có năm và cả cụm chỉ có
đúng 1 năm xác định). Năm khác nhau = sự kiện khác -> KHÔNG đụng
('điện biên phủ' 1954 vs 'điện biên phủ trên không' 1972 khác cả khoá lẫn năm).

Cổng `kind` chặn gộp chéo loại: 'Chiến dịch Hồ Chí Minh' (campaign) sau khi bỏ tiền tố
cũng ra khoá 'hochiminh' như nhân vật 'Hồ Chí Minh' (person) — khác kind nên KHÔNG gộp.

Bản GOLD (chép từ ghi chú người dùng) LUÔN là bản sống sót và facts của nó đứng TRƯỚC.
Reversible: backup toàn bộ property + cạnh của node bị gộp ra JSON trước khi xoá.
Chạy `--dry` để chỉ xem, không ghi."""
import json, os, re, sys, unicodedata
from collections import defaultdict, Counter
from neo4j import GraphDatabase

BATCH = "hist_consolidate_2026_09_05"
HERE = os.path.dirname(os.path.abspath(__file__))
DRY = "--dry" in sys.argv
PREFIX = ["cuoc khoi nghia", "cuoc khang chien", "cuoc cach mang", "cuoc chien tranh",
          "cuoc tien cong", "cuoc dau tranh", "phong trao", "chien dich", "chien thang",
          "khoi nghia", "khang chien", "cuoc"]
FILLER = ["xam luoc"]


def fold(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").replace("đ", "d")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s)).strip()


def ekey(name):
    s = re.sub(r"\(.*?\)", " ", name or "")          # bỏ cụm trong ngoặc
    s = fold(s)
    for f in FILLER:
        s = s.replace(f" {f} ", " ")
    for p in PREFIX:                                  # bỏ 1 tiền tố loại chung
        if s.startswith(p + " ") and len(s) - len(p) > 8:
            s = s[len(p) + 1:]
            break
    return s.replace(" ", "")


drv = GraphDatabase.driver(os.getenv("EDU_NEO4J_URI", "bolt://localhost:7688"),
                           auth=(os.getenv("EDU_NEO4J_USER", "neo4j"), os.environ["EDU_NEO4J_PASS"]))
with drv.session() as s:
    nodes = s.run("""MATCH (h:HistEvent) WHERE h.verified=true
                     RETURN elementId(h) AS e, h.canonical_name AS n, h.name_norm AS nn,
                            h.year AS y, h.source_tier AS t, h.grade AS g, h.grades AS gs,
                            coalesce(h.kind,'event') AS kind,
                            h.facts AS facts, h.traps AS traps, h.sources AS src,
                            coalesce(h.summary,'') AS sm""").data()
    print(f"HistEvent verified: {len(nodes)}")

    groups = defaultdict(list)
    for h in nodes:
        groups[(ekey(h["n"]), h["kind"])].append(h)

    plans, stat = [], Counter()
    for (k, kind), g in groups.items():
        if len(g) < 2 or not k:
            continue
        ys = sorted({h["y"] for h in g if h["y"] not in (None, -99999)})
        if len(ys) > 1:
            # cùng khoá nhưng NHIỀU năm -> chỉ gộp trong từng năm
            sub = defaultdict(list)
            for h in g:
                sub[h["y"] if h["y"] not in (None, -99999) else "?"].append(h)
            buckets = [v for kk, v in sub.items() if kk != "?" and len(v) > 1]
            stat["cụm nhiều năm -> gộp theo từng năm"] += 1
        else:
            buckets = [g]                     # 1 năm xác định (hoặc không năm) -> gộp cả cụm
        for b in buckets:
            if len(b) < 2:
                continue
            # bản sống sót: GOLD trước -> CÓ NĂM trước (giữ được mốc để lọc theo năm)
            # -> nhiều facts nhất. Facts của các bản bị gộp vẫn được hợp nhất vào.
            b.sort(key=lambda h: (0 if h["t"] == "gold" else 1,
                                  0 if h["y"] not in (None, -99999) else 1,
                                  -len(h.get("facts") or []), -len(h.get("sm") or "")))
            plans.append((f"{k}|{kind}", b[0], b[1:]))
            stat["cụm gộp"] += 1
            stat["node bị gộp"] += len(b) - 1

    print(f"cụm cần gộp: {len([p for p in plans])} | node sẽ biến mất: {stat['node bị gộp']}")
    for k, keep, lose in plans:
        print(f"  [{k[:34]:<36}] GIỮ {str(keep['n'])[:44]:<46} ({keep['t']},{len(keep.get('facts') or [])}f,y={keep['y']})")
        for l in lose:
            print(f"      + gộp {str(l['n'])[:44]:<46} ({l['t']},{len(l.get('facts') or [])}f,y={l['y']})")
    if DRY:
        sys.exit(0)

    backup = []
    for k, keep, lose in plans:
        ids = [l["e"] for l in lose]
        backup += s.run("""MATCH (h:HistEvent) WHERE elementId(h) IN $ids
                           RETURN elementId(h) AS e, properties(h) AS p,
                                  [(a:HistAlias)-[:ALIAS_OF]->(h) | a.value_norm] AS aliases,
                                  [(l:HistLesson)-[:HAS_EVENT]->(h) | elementId(l)] AS lessons
                        """, ids=ids).data()
        # facts: bản sống sót TRƯỚC, rồi bổ sung của các bản bị gộp (khử trùng)
        seen, facts = set(), []
        for h in [keep] + lose:
            for f in (h.get("facts") or []):
                kk = fold(f)[:80]
                if kk and kk not in seen:
                    seen.add(kk); facts.append(f)
        traps, seen_t = [], set()
        for h in [keep] + lose:
            for t in (h.get("traps") or []):
                kk = fold(t)[:80]
                if kk and kk not in seen_t:
                    seen_t.add(kk); traps.append(t)
        grades = sorted({x for h in [keep] + lose
                         for x in ((h.get("gs") or []) + ([h["g"]] if h.get("g") else []))})
        srcs, seen_s = [], set()
        for h in [keep] + lose:
            for x in (h.get("src") or []):
                if x not in seen_s:
                    seen_s.add(x); srcs.append(x)
        s.run("""MATCH (h) WHERE elementId(h)=$e
                 SET h.facts=$f, h.traps=$tr, h.grades=$gs, h.sources=$src,
                     h.consolidated_batch=$b""",
              e=keep["e"], f=facts[:18], tr=traps[:8], gs=grades, src=srcs[:10], b=BATCH)
        # chuyển alias + cạnh bài sang bản sống sót rồi xoá bản thừa
        s.run("""MATCH (h:HistEvent) WHERE elementId(h) IN $ids
                 MATCH (a:HistAlias)-[:ALIAS_OF]->(h)
                 MATCH (k) WHERE elementId(k)=$keep
                 MERGE (a)-[:ALIAS_OF]->(k)""", ids=ids, keep=keep["e"])
        s.run("""MATCH (h:HistEvent) WHERE elementId(h) IN $ids
                 MATCH (l:HistLesson)-[:HAS_EVENT]->(h)
                 MATCH (k) WHERE elementId(k)=$keep
                 MERGE (l)-[r:HAS_EVENT]->(k) ON CREATE SET r.batch=$b""",
              ids=ids, keep=keep["e"], b=BATCH)
        s.run("MATCH (h:HistEvent) WHERE elementId(h) IN $ids DETACH DELETE h", ids=ids)

    json.dump(backup, open(f"{HERE}/consolidate_backup.json", "w"), ensure_ascii=False, indent=1)
    print(f"\nđã gộp {len(plans)} cụm, xoá {len(backup)} node (backup consolidate_backup.json)")
    orph = s.run("MATCH (a:HistAlias) WHERE NOT (a)-[:ALIAS_OF]->() DETACH DELETE a RETURN count(*) AS c").single()["c"]
    print(f"xoá {orph} alias mồ côi")
    print("HistEvent verified còn:", s.run("MATCH (h:HistEvent {verified:true}) RETURN count(*) AS c").single()["c"])
    print("HAS_EVENT:", s.run("MATCH ()-[r:HAS_EVENT]->() RETURN count(*) AS c").single()["c"])
    print(f"Rollback: khôi phục từ consolidate_backup.json (batch {BATCH})")
