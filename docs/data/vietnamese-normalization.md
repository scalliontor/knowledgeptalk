# Vietnamese Normalization — `fold()` / NFD (rủi ro anchoring chính)

> **Tại sao file này tồn tại**: anchoring Sử/Toán tụt chủ yếu khi tên bài chứa dấu/đ/số La Mã mà query khớp **không qua fold**. Neo4j lưu `work_name` ở dạng **NFD** (Unicode decomposed). Match trực tiếp bằng `(?i)` / `STARTS WITH` / so chuỗi thô sẽ **fail CÂM** (không lỗi, chỉ trả rỗng → tụt anchor).
> **Nguồn code thực**: `rag_edu/scripts/schema_v3_2026_06/build_book_generic.py` (`fold`, `wslug`), `backfill_worknorm.py`, `diag_weak.py` — cả ba định nghĩa `fold()` GIỐNG HỆT nhau.

## 1. Hàm chuẩn `fold()` (3 file dùng chung — phải GIỐNG)

```python
import unicodedata
def fold(s):
    s = (s or "").replace("đ", "d").replace("Đ", "D")   # 1) đ/Đ -> d/D (NFD KHÔNG tách được đ)
    s = unicodedata.normalize("NFD", s)                  # 2) tách dấu thành combining marks
    return "".join(c for c in s
                   if unicodedata.category(c) != "Mn"    # 3) bỏ mọi dấu (Mark, nonspacing)
                  ).lower()                              # 4) lower
```

`wslug()` (cho id/slug) = `fold()` rồi thay mọi ký tự không phải `[a-z0-9]` bằng `-`:
```python
def wslug(s): return re.sub(r"-+","-", re.sub(r"[^a-z0-9]+","-", fold(s))).strip("-")
```

Ví dụ:
- `"Khởi nghĩa Lam Sơn"` → `"khoi nghia lam son"`
- `"Định lí Py-ta-go"` → `"dinh li py-ta-go"`
- `"Số hữu tỉ"` → `"so huu ti"`
- `"Việt Nam từ năm 1954 đến 1965"` → `"viet nam tu nam 1954 den 1965"` (`đ`→`d`)

## 2. ⚠️ Bẫy đ/Đ (lý do bước 1 phải có RIÊNG)

`unicodedata.normalize("NFD", "đ")` **KHÔNG** tách `đ` thành `d` + dấu — `đ` là một code point độc lập (U+0111), không phải `d` + combining. Nếu bỏ bước `.replace("đ","d")` thì `"đường tròn"` fold ra `"đuong tron"` (vẫn còn `đ`), query `"duong tron"` sẽ **không khớp** → fail câm. Đây là một trong các nguyên nhân Sử/Toán lệch (tên bài chứa "đến", "đường", "đồ thị", "định lí", "đa thức", "đơn thức"...).

## 3. Hợp đồng match (CẢ HAI ĐẦU phải fold)

Neo4j lưu:
- `work_name` = NFD, có dấu (KHÔNG match được thẳng).
- `work_name_norm` = `fold(work_name)` — backfill bởi `backfill_worknorm.py` (`SET k.work_name_norm = fold(k.work_name)`); tương tự `:Concept.name_norm`, `:LiteraryWork.name_norm`.

Query phải:
1. `qf = fold(user_query)` ở phía Python TRƯỚC khi vào Cypher.
2. So bằng **property đã fold**: `WHERE $qf CONTAINS k.work_name_norm` (xem `diag_weak.py` Văn) hoặc `WHERE q CONTAINS c.name_norm` (Toán concept).

```cypher
// ĐÚNG (từ diag_weak.py): cả hai đầu đã fold
MATCH (k:KnowledgeChunk {subject_code:'ngu_van', production_ready:true})
WHERE (k.grade=$g OR toString(k.grade)=toString($g)) AND k.bo_sach=$bo
  AND k.work_name_norm IS NOT NULL
  AND $qf CONTAINS k.work_name_norm        // $qf = fold(query); work_name_norm = fold(work_name)
  AND k.variant = $var
RETURN k LIMIT 1;
```

## 4. ❌ Anti-pattern — fail CÂM (đừng dùng)

```cypher
-- SAI 1: regex case-insensitive trên work_name NFD
WHERE k.work_name =~ ('(?i).*' + $query + '.*')      -- $query có dấu khác NFD storage -> miss

-- SAI 2: STARTS WITH / CONTAINS trên field NFD bằng query người gõ
WHERE k.work_name STARTS WITH $query                 -- "Định lí" (NFC user) ≠ "Định lí" (NFD store)

-- SAI 3: toLower nhưng KHÔNG strip dấu / KHÔNG đổi đ->d
WHERE toLower(k.work_name) CONTAINS toLower($query)   -- dấu + đ vẫn lệch
```

Tất cả trả **rỗng mà không báo lỗi** → bug câm, chỉ lộ qua anchor tụt trong backtest.

> **Lưu ý NFC vs NFD ở phía client**: chuỗi người dùng/STT thường ở **NFC**; storage ở **NFD**. So sánh `=` hai chuỗi "trông giống nhau" vẫn false. `fold()` chuẩn hóa cả hai về cùng một dạng không-dấu → khử luôn vấn đề NFC/NFD.

## 5. Liên hệ điểm yếu thật

- **Lịch sử 9 CTST** (current_lesson 79.0%, headline 73.2%) và **Lịch sử 9 KNTT** (cl 88.2%): tên bài chứa **năm, gạch ngang, số La Mã, "đến/đầu/đường"** → nghi `work_name_norm` lệch hoặc query không fold đủ. Check Q-MISS + đối chiếu fold tay vài bài.
- **Toán 8 CTST t1** (cl 76.8%): tên bài Toán dài/định dạng lạ ("Bài N trang M" lẫn lesson) — vừa là F1 collision vừa có thể fold edge-case.
- Số La Mã (`Chương I`, `thế kỉ XV`) **KHÔNG** được fold đổi sang Ả Rập — `"xv"` giữ nguyên; nếu query đọc "thế kỷ mười lăm" sẽ không khớp `"the ki xv"`. Đây là khoảng trống cần normalize tay nếu xuất hiện (chưa xử lý trong `fold()`).

## 6. Test nhanh (để chạy sau, read-only)

```python
# Đối chiếu work_name_norm trong DB có đúng = fold(work_name) không (drift detector)
# (chạy sau, chỉ MATCH/RETURN; so ở Python)
# MATCH (l:Lesson) WHERE l.work_name_norm <> fold(l.work_name)  -> nhưng Cypher không có fold(),
# nên: kéo (work_name, work_name_norm) về Python, so fold(work_name) == work_name_norm.
```

```cypher
// Số :Lesson có work_name nhưng THIẾU work_name_norm (chắc chắn fail anchor tên bài)
MATCH (l:Lesson) WHERE l.work_name IS NOT NULL AND l.work_name_norm IS NULL
RETURN l.subject_code AS s, l.grade AS g, count(l) AS thieu_norm ORDER BY thieu_norm DESC;
```

---
Liên quan: `rag_edu/scripts/schema_v3_2026_06/{build_book_generic,backfill_worknorm,diag_weak}.py` · `docs/data/neo4j-schema-v3.md` (§4 anchor fields) · `docs/data/data-quality-checklist.md` (Q-MISS) · MEMORY "_fold unidecode bug fixed"
