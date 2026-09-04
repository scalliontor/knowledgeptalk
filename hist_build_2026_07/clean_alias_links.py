# -*- coding: utf-8 -*-
"""Gỡ liên kết ALIAS_OF SAI ĐỊA CHỈ (data-only, reversible).

BỆNH: thẻ rộng liệt kê tên các thực thể được NHẮC TỚI trong thẻ vào ô `aliases`.
Thẻ 'Triều Nguyễn (1802-1945)' có alias 'dục đức'; thẻ 'Triều Hậu Lê' có alias
'luật hồng đức'. Alias trỏ nhiều thẻ KHÁC NĂM -> query_hist_event() thấy nhập nhằng
-> trả None (nhường tầng dưới) hoặc hỏi lại, dù có thẻ đúng ngay đó.

LUẬT GỠ (rất hẹp, có kiểm chứng ngược — không phải chuẩn-hoá đại trà):
  gỡ (a)-[:ALIAS_OF]->(X) khi VÀ CHỈ KHI
    (1) mọi token của `a` KHÔNG nằm trong chính tên X, VÀ
    (2) tồn tại thẻ Y khác mà mọi token của `a` NẰM TRONG tên Y
  -> tức là: alias này rõ ràng là tên của Y, không phải tên của X.
Nếu không tìm được Y nào (alias không là tên của thẻ nào) thì GIỮ NGUYÊN — thà
nhập nhằng còn hơn cắt mất đường vào. Thẻ chỉ còn 0 alias cũng được giữ lại link.

Chạy `--dry` để xem danh sách trước."""
import json, os, re, sys, unicodedata
from collections import defaultdict
from neo4j import GraphDatabase

BATCH = "alias_unlink_2026_09_05"
HERE = os.path.dirname(os.path.abspath(__file__))
DRY = "--dry" in sys.argv


def fold(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").replace("đ", "d")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s)).strip()


def inside(a, name):
    """mọi token của alias xuất hiện trong tên thẻ (theo ranh giới từ)."""
    nf = " " + fold(name) + " "
    return all(f" {t} " in nf for t in a.split())


drv = GraphDatabase.driver(os.getenv("EDU_NEO4J_URI", "bolt://localhost:7688"),
                           auth=(os.getenv("EDU_NEO4J_USER", "neo4j"), os.environ["EDU_NEO4J_PASS"]))
with drv.session() as s:
    links = s.run("""MATCH (a:HistAlias)-[r:ALIAS_OF]->(h:HistEvent)
                     WHERE h.verified=true
                     RETURN a.value_norm AS a, elementId(a) AS ae,
                            elementId(h) AS he, h.canonical_name AS n, h.year AS y""").data()
    by = defaultdict(list)
    for l in links:
        by[l["a"]].append(l)

    cut, keep_no_owner = [], 0
    for a, ls in by.items():
        if len(ls) < 2:
            continue
        ys = {l["y"] for l in ls if l["y"] not in (None, -99999)}
        if len(ys) < 2:
            continue                       # cùng năm -> tầng gộp-trùng đã lo
        owners = [l for l in ls if inside(a, l["n"])]
        if not owners:
            keep_no_owner += 1
            continue                       # không xác định được chủ -> GIỮ NGUYÊN
        for l in ls:
            if l not in owners:
                cut.append(l)

    print(f"alias trỏ >1 thẻ & KHÁC NĂM: {sum(1 for a,ls in by.items() if len(ls)>1 and len({l['y'] for l in ls if l['y'] not in (None,-99999)})>1)}")
    print(f"  không xác định được chủ -> giữ nguyên: {keep_no_owner}")
    print(f"  liên kết SAI ĐỊA CHỈ sẽ gỡ: {len(cut)}")
    for l in cut[:35]:
        print(f"    gỡ {l['a'][:30]:<32} khỏi  {str(l['n'])[:50]:<52} (y={l['y']})")
    if len(cut) > 35:
        print(f"    ... còn {len(cut)-35}")
    if DRY or not cut:
        sys.exit(0)

    json.dump(cut, open(f"{HERE}/alias_unlink_backup.json", "w"), ensure_ascii=False, indent=1)
    n = s.run("""UNWIND $rows AS row
                 MATCH (a:HistAlias)-[r:ALIAS_OF]->(h:HistEvent)
                 WHERE elementId(a)=row.ae AND elementId(h)=row.he
                 DELETE r RETURN count(*) AS c""", rows=cut).single()["c"]
    print(f"\nđã gỡ {n} liên kết (backup alias_unlink_backup.json, batch {BATCH})")
    orph = s.run("MATCH (a:HistAlias) WHERE NOT (a)-[:ALIAS_OF]->() DETACH DELETE a RETURN count(*) AS c").single()["c"]
    print(f"xoá {orph} alias mồ côi")
    print("Rollback: đọc alias_unlink_backup.json rồi MERGE lại (a)-[:ALIAS_OF]->(h) theo elementId")
