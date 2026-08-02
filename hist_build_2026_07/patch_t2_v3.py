# -*- coding: utf-8 -*-
"""Port 4 sửa (đã đo offline: 12/40 -> 29/40) vào rag_server_canary8892.py:
 (1) KHỚP RANH GIỚI TỪ — bug nặng: alias 'un' khớp giữa từ 'xây dựng' -> trả 'Liên hợp quốc'
 (2) GỘP TRÙNG-LẶP-DỮ-LIỆU — cùng sự kiện tách nhiều node (biến thể tên / lặp theo lớp):
     chỉ coi NHẬP NHẰNG THẬT khi các ứng viên có NĂM XÁC ĐỊNH KHÁC NHAU
 (3) SIBLING-GUARD chỉ hỏi lại khi anh-em là SỰ KIỆN KHÁC NĂM (trước: mọi biến thể tên đều hỏi)
 (4) FALLBACK token-subset siết: >=3 token VÀ tối đa 2 từ lạ chèn giữa"""
import py_compile, sys
F = "/home/namnx/Ptalk_project/CloudPTalk/rag_server_canary8892.py"
import shutil
shutil.copyfile(F, F + ".bak_pre_t2v3_20260802")
src = open(F, encoding="utf-8").read()
n = 0

# (1) ranh giới từ cho truy vấn chính
OLD = "WHERE h.verified = true AND $qf CONTAINS a.value_norm"
NEW = "WHERE h.verified = true AND (' '+$qf+' ') CONTAINS (' '+a.value_norm+' ')"
assert OLD in src, "(1)"; src = src.replace(OLD, NEW, 1); n += 1

# (2) gộp trùng cùng-năm trước khi kết luận nhập nhằng
OLD = """    best_len = len(rows[0]["alias"])
    top = [r for r in rows if len(r["alias"]) >= best_len]           # cùng độ dài alias dài nhất
    others = [r for r in rows if len(r["alias"]) < best_len]"""
NEW = """    best_len = len(rows[0]["alias"])
    top = [r for r in rows if len(r["alias"]) >= best_len]           # cùng độ dài alias dài nhất
    others = [r for r in rows if len(r["alias"]) < best_len]

    # GỘP TRÙNG-LẶP-DỮ-LIỆU: cùng một sự kiện có thể bị tách thành nhiều node (biến thể tên,
    # lặp theo lớp/bộ sách). Chỉ coi là NHẬP NHẰNG THẬT khi các ứng viên có NĂM XÁC ĐỊNH KHÁC NHAU.
    def _yv(r):
        y = r.get("year")
        return None if y in (None, -99999) else y
    _ys_top = {_yv(r) for r in top if _yv(r) is not None}
    if len(top) > 1 and len(_ys_top) <= 1:
        top = [max(top, key=lambda r: (len(r.get("facts") or []), len(r.get("summary") or "")))]"""
assert OLD in src, "(2)"; src = src.replace(OLD, NEW, 1); n += 1

# (3) sibling-guard: chỉ khi khác NĂM
OLD = """                MATCH (a:HistAlias)-[:ALIAS_OF]->(h:HistEvent)
                WHERE h.verified = true AND a.value_norm STARTS WITH $base
                  AND a.value_norm <> $base AND h.name_norm <> $nn
                RETURN DISTINCT h.canonical_name AS name, h.year AS year LIMIT 4
            \"\"\", base=base, nn=top[0]["nn"]).data()"""
NEW = """                MATCH (a:HistAlias)-[:ALIAS_OF]->(h:HistEvent)
                WHERE h.verified = true AND a.value_norm STARTS WITH $base
                  AND a.value_norm <> $base AND h.name_norm <> $nn
                  AND h.year IS NOT NULL AND h.year <> -99999
                  AND ($y IS NULL OR abs(h.year - $y) > 1)
                RETURN DISTINCT h.canonical_name AS name, h.year AS year LIMIT 4
            \"\"\", base=base, nn=top[0]["nn"],
                 y=(None if top[0].get("year") in (None, -99999) else top[0].get("year"))).data()"""
assert OLD in src, "(3)"; src = src.replace(OLD, NEW, 1); n += 1

# (4) fallback token-subset siết
OLD = """        def _subseq(alias):
            at = alias.split()
            if len(at) < 2: return False
            j = 0
            for t in qtok:
                if j < len(at) and t == at[j]: j += 1
            return j == len(at)"""
NEW = """        def _subseq(alias):
            at = alias.split()
            if len(at) < 3: return False        # >=3 token (chống khớp bậy)
            j = 0; first = None; last = None
            for i, t in enumerate(qtok):
                if j < len(at) and t == at[j]:
                    if first is None: first = i
                    last = i; j += 1
            if j != len(at): return False
            return (last - first + 1) - len(at) <= 2   # tối đa 2 từ lạ chèn giữa"""
assert OLD in src, "(4)"; src = src.replace(OLD, NEW, 1); n += 1

open(F, "w", encoding="utf-8").write(src)
py_compile.compile(F, doraise=True)
print(f"OK {n}/4 edit | py_compile PASS | backup {F}.bak_pre_t2v3_20260802")
