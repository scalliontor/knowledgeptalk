# -*- coding: utf-8 -*-
"""Vá 7 bài tiểu học bị 'not_found' do Gemma bóc tên khác với tên SGK (data-only).

BỆNH: query_lesson_card neo bằng `$qf CONTAINS l.work_name_norm` — chuỗi Gemma bóc
phải CHỨA TRỌN tên đã lưu. Gemma hay phiên âm lại tên nước ngoài (in-tơ-nét ->
Internet), cắt chữ (Bước mùa xuân -> Bước xuân), hoặc bỏ tiền tố (Phim hoạt hình
Chú ốc sên bay -> Chú ốc sên bay) => trượt.

CÁCH VÁ:
  (1) 6 bài: thêm :Lesson ALIAS (work_name_norm = dạng Gemma hay trả / tiền tố chung)
      cùng trỏ HAS_THEORY vào ĐÚNG KnowledgeChunk gốc. Giữ nguyên tên SGK ở bài gốc.
  (2) 1 bài: ĐỔI TÊN thật — "Cái gì quý nhất ?" có dấu cách thừa trước '?' (lỗi nhập
      từ TSV; SGK viết liền). Sửa cả work_name lẫn work_name_norm để giữ bất biến
      work_name_norm == _fold(work_name).

CỔNG CHỐNG CƯỚP BÀI (bài học alias 'un' khớp trong 'xây dựng'):
  - alias >= 8 ký tự
  - alias KHÔNG được là chuỗi con của work_name_norm bài nào khác
  - alias KHÔNG được trùng work_name_norm đã có
  Vi phạm bất kỳ điều nào -> BỎ QUA bài đó, in cảnh báo, không ghi.

Reversible: alias node tag ingest_batch; đổi tên lưu giá trị cũ vào work_name_orig.
  python3 fix_cap1_aliases.py [--dry]"""
import json, os, sys, unicodedata

BATCH = os.getenv("ALIAS_BATCH", "cap1_alias_2026_09_05")
DRY = "--dry" in sys.argv

def _fold(s):
    """BẢN SAO _fold() của prod."""
    s = (s or "").replace("đ", "d").replace("Đ", "D").replace("–", "-")
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn").lower()

# (tên bài gốc trong kho, alias cần thêm, lý do)
# ĐỢT 1 (tiền tố) — phục vụ nhánh `$qf CONTAINS work_name_norm`, chỉ chạy khi Gemma
# KHÔNG bóc được tên bài. Giữ lại vì vô hại và có ích ở nhánh đó.
# ĐỢT 2 (trùng khít) — nhánh THẬT SỰ chạy khi Gemma bóc được tên là
# `l.work_name_norm = $cur_norm` (BẰNG CHÍNH XÁC), nên alias phải khớp từng ký tự
# với chuỗi Gemma trả. Các chuỗi dưới đây đo bằng cách hỏi prod 4-6 lần/bài.
ALIASES = [
    ("Từ chú bồ câu đến in-tơ-nét",                 "tu chu bo cau den",             "[đợt1] tiền tố chung"),
    ("Khu bảo tồn động vật hoang dã Ngô-rông-gô-rô", "khu bao ton dong vat hoang da",  "[đợt1] tiền tố chung"),
    ("Tinh thần học tập của nhà Phi-lít",            "tinh than hoc tap cua nha",      "[đợt1] tiền tố chung"),
    ("Bước mùa xuân",                                "buoc xuan",                      "Gemma rụng chữ 'mùa' (3/6 lần)"),
    ("Phim hoạt hình Chú ốc sên bay",                "chu oc sen bay",                 "Gemma bỏ tiền tố 'Phim hoạt hình'"),
    ("Ngu Công xã Trịnh Tường",                      "ngu cong diet trinh tuong",      "Gemma đổi 'xã'->'diệt'"),
    # đợt 2 — trùng khít chuỗi Gemma
    ("Từ chú bồ câu đến in-tơ-nét",                 "tu chu bo cau den internet",     "Gemma La-tinh hoá 'in-tơ-nét'->'Internet' (3/6 lần)"),
    ("Khu bảo tồn động vật hoang dã Ngô-rông-gô-rô", "khu bao ton dong vat hoang da ngorongoro", "Gemma La-tinh hoá 'Ngô-rông-gô-rô'->'Ngorongoro' (4/4 lần — LUÔN trượt)"),
    ("Cái gì quý nhất?",                             "cai gi quy nhat",                "Gemma bỏ dấu '?' cuối tên (6/6 lần)"),
]
# đổi tên thật: (tên cũ, tên mới) — chỉ được phép bỏ khoảng trắng thừa trước dấu câu
RENAMES = [("Cái gì quý nhất ?", "Cái gì quý nhất?")]

from neo4j import GraphDatabase
drv = GraphDatabase.driver(os.getenv("EDU_NEO4J_URI", "bolt://localhost:7688"),
                           auth=(os.getenv("EDU_NEO4J_USER", "neo4j"), os.environ["EDU_NEO4J_PASS"]))

with drv.session() as s:
    all_norms = {r["n"] for r in s.run(
        "MATCH (l:Lesson) WHERE l.work_name_norm IS NOT NULL RETURN DISTINCT l.work_name_norm AS n").data()}
    all_norms |= {r["n"] for r in s.run(
        "MATCH (t:LiteratureText) WHERE t.work_name_norm IS NOT NULL RETURN DISTINCT t.work_name_norm AS n").data()}
    print(f"kho hiện có {len(all_norms)} work_name_norm phân biệt\n")

    created, refused = [], []
    for work, alias, why in ALIASES:
        wnn = _fold(work)
        errs = []
        if len(alias) < 8:
            errs.append(f"alias quá ngắn ({len(alias)})")
        if alias in all_norms:
            errs.append("alias TRÙNG work_name_norm đã có")
        # alias là chuỗi con của bài KHÁC -> câu hỏi bài kia sẽ kéo nhầm sang đây
        clash = [n for n in all_norms if n != wnn and alias in n]
        if clash:
            errs.append(f"alias nằm trong {len(clash)} bài khác: {clash[:3]}")
        if errs:
            refused.append((work, alias, errs)); continue

        src = s.run("""MATCH (l:Lesson {work_name_norm:$wnn})-[:HAS_THEORY]->(k:KnowledgeChunk)
                       RETURN elementId(l) AS le, elementId(k) AS ke, l.grade AS g,
                              l.work_name AS w LIMIT 1""", wnn=wnn).single()
        if not src:
            refused.append((work, alias, ["KHÔNG tìm thấy bài gốc trong kho"])); continue
        print(f"✓ {work}")
        print(f"    alias  : {alias!r}")
        print(f"    vì     : {why}")
        if DRY:
            continue
        r = s.run("""MERGE (a:Lesson {lesson_id:$lid})
                     ON CREATE SET a._new=true
                     SET a.subject_code='ngu_van', a.work_name=$w, a.work_name_norm=$alias,
                         a.grade=$g, a.title=$w, a.ingest_actor='VAN_CAP1_ALIAS_2026_09_05',
                         a.ingest_batch=$b, a.alias_of=$wnn
                     WITH a MATCH (k) WHERE elementId(k)=$ke
                     MERGE (a)-[rel:HAS_THEORY]->(k) ON CREATE SET rel.batch=$b
                     RETURN elementId(a) AS e""",
                  lid=f"vancap1alias:{src['g']}:{alias}", w=src["w"], alias=alias,
                  g=src["g"], ke=src["ke"], b=BATCH, wnn=wnn).single()
        s.run("MATCH (a) WHERE elementId(a)=$e REMOVE a._new", e=r["e"])
        created.append({"work": work, "alias": alias, "e": r["e"]})

    print()
    for work, alias, errs in refused:
        print(f"✗ BỎ QUA {work}: {errs}")

    # ── đổi tên thật ──
    renamed = []
    for old, new in RENAMES:
        # GATE: chỉ được bỏ khoảng trắng thừa, không được đổi gì khác
        if old.replace(" ", "") != new.replace(" ", ""):
            print(f"✗ ĐỔI TÊN BỊ CHẶN (khác hơn khoảng trắng): {old!r} -> {new!r}"); continue
        on, nn = _fold(old), _fold(new)
        cur = s.run("""MATCH (l:Lesson {work_name_norm:$on})
                       RETURN elementId(l) AS e, l.work_name AS w""", on=on).data()
        if not cur:
            print(f"✗ không thấy bài {old!r} để đổi tên"); continue
        if DRY:
            print(f"\n✓ ĐỔI TÊN {old!r} -> {new!r}  ({len(cur)} node)"); continue
        for c in cur:
            s.run("""MATCH (l) WHERE elementId(l)=$e
                     SET l.work_name_orig=coalesce(l.work_name_orig, l.work_name),
                         l.work_name_norm_orig=coalesce(l.work_name_norm_orig, l.work_name_norm),
                         l.work_name=$new, l.work_name_norm=$nn, l.title=$new,
                         l.renamed_batch=$b""", e=c["e"], new=new, nn=nn, b=BATCH)
            renamed.append({"old": old, "new": new, "e": c["e"]})
        print(f"\n✓ ĐỔI TÊN {old!r} -> {new!r}  ({len(cur)} node)")

if not DRY:
    HERE = os.path.dirname(os.path.abspath(__file__))
    json.dump({"batch": BATCH, "aliases": created, "renamed": renamed, "refused":
               [{"work": w, "alias": a, "errs": e} for w, a, e in refused]},
              open(f"{HERE}/fix_cap1_aliases_backup.json", "w"), ensure_ascii=False, indent=1)
    print(f"\nTạo {len(created)} alias | đổi tên {len(renamed)} | từ chối {len(refused)}")
    print(f"Rollback alias : MATCH (n) WHERE n.ingest_batch='{BATCH}' DETACH DELETE n")
    print(f"Rollback tên   : SET l.work_name=l.work_name_orig, l.work_name_norm=l.work_name_norm_orig")
