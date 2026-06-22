# Anchoring — phương pháp routing hiện tại (as-built)

> **Mục đích**: mô tả CHÍNH XÁC thứ tự ưu tiên neo bài (anchor) đang chạy, để mọi đề xuất vá Toán tiểu học / Lịch sử có gốc chung. Không đổi behavior — đây là tài liệu mô tả.
>
> **Nguồn sự thật**: runtime KHÔNG ở repo này (single-file `rag_server.py`/`rag_server_canary.py` trên server). Tài liệu này tái dựng từ: các patch script trong `rag_edu/scripts/schema_v3_2026_06/` (`patch_tc_canary.py`, `patch_tc2_concept_match.py`), scorer `backtest_book.py`, và các pilot docs (`docs/pilot/RESULTS.md`, `TOAN_v6_ctst_t2_RESULTS.md`, `BACKTEST_RULE.md`, `MULTISUBJECT_SCALE_2026_06_14.md`). Các con số gate dưới đây là **đã commit trong docs/script**, không phải đọc trực tiếp từ server file.

## 0. Hai loại tín hiệu vào

Mỗi request `/retrieve` mang:
- `query` (chuỗi học sinh nói).
- `user_profile` (client gửi): có thể chứa `current_lesson` (tên bài đang mở), `trang`, và scope `lop` / `bo_sach` / `subject` / `tap`.

Trong backtest, scope luôn được set (`lop`, `bo_sach`, `subject`); `current_lesson` và `trang` chỉ có ở các dimension tương ứng. Production thật (Kid-mentor) gửi `current_lesson`/`trang` ⇒ chạy đường anchored. Khi client gửi `{}` (gap #4 trong canonical) thì tụt về content-vector.

## 1. Thứ tự ưu tiên neo bài (structured-first)

Theo invariant canonical (`current_lesson → tên bài → trang+tập → content-vector`) và mã patch:

| Bậc | Tín hiệu | Cơ chế | Độ tin |
|---|---|---|---|
| **1. current_lesson** | `user_profile.current_lesson` = tên bài | client khẳng định bài đang mở → lookup `:Lesson` theo `work_name` trong scope | deterministic, gần như tuyệt đối |
| **2. tên bài trong câu** | query chứa tên bài/tác phẩm | regex/parse tên → match `work_name`; với Toán/KHTN là **concept name** (`query_concept_exact`) | deterministic nếu tên khớp norm |
| **3. trang (+tập)** | `trang` trong câu hoặc `user_profile.trang` | lookup `:Lesson` mà `trang_from ≤ trang ≤ trang_to`, scoped `bo_sach + tap_no` | deterministic, phụ thuộc biên trang đúng |
| **4. content-vector** | không có 1–3 | BGE cosine giữa query và theory-embedding của các bài trong scope, có **gate** (mục 3) | xác suất; ca khó nhất |

Bậc 1–3 = **structured/Tier A**. Bậc 4 = fallback. Tier A-concept (`query_concept_exact`, mục 4) nằm giữa bậc 2–4: chỉ kích hoạt khi **không** có `bai_no`/`trang` nhưng có `lop`+`bo_sach`.

## 2. Scope (luôn áp ở mọi bậc)

Match được giới hạn bởi:
- `subject_code` (thêm ở pilot Toán 6 — chống va trang Toán↔Văn cùng grade+book+tap; `subject IS NULL` → khớp mọi môn, backward-compat Văn).
- `grade` (T-C patch `patch_tc_canary.py` PATCH1: fix `intent["grade"]` propagate từ `parsed["lop"]` — vá cross-grade leak; retrieval đọc `intent["grade"]` còn parse trả `lop`).
- `bo_sach` (CTST/KNTT/CD).
- `tap_no` (chống trùng số trang giữa tập 1 và tập 2 — page reset xử lý theo `tap_no`).

Cypher Tier A-concept (từ `patch_tc2_concept_match.py`) minh hoạ scope + match:
```
MATCH (k:KnowledgeChunk)-[:COVERS]->(c:Concept)
WHERE coalesce(k.production_ready,false)=true
  AND (k.grade=$grade OR toString(k.grade)=toString($grade))
  AND k.bo_sach=$bo_sach
  AND ($subject IS NULL OR k.subject_code=$subject)
  AND c.name_norm IS NOT NULL AND size(c.name_norm) >= 3
WITH k,c,$q_folded AS q
WITH k,c,q,[w IN split(c.name_norm,' ') WHERE size(w)>=4] AS cw
WITH k,c,q,cw,[w IN cw WHERE q CONTAINS w] AS hits
WHERE q CONTAINS c.name_norm OR (size(cw)>=2 AND size(hits)>=2)
...ORDER BY mscore DESC, (vietjack_lesson first), clen DESC, size(text) DESC LIMIT 3
```

## 3. Content-vector gate (bậc 4)

Để fallback BGE không "ép card" cho chitchat/bài ngoài sách, có **gate** trên best-score (`bs`) và margin (top1 − top2):

- **Văn gốc** (`docs/pilot/RESULTS.md`): `margin top1−top2 ≥ 0.03`.
- **Toán pilot nới** (`docs/pilot/TOAN_v6_ctst_t2_RESULTS.md`): `bs>=0.46 AND (margin>=0.03 OR bs>=0.52)` — vì các bài cùng chương Toán embed na ná nhau (top1≈top2) khiến gate Văn cũ loại nhầm → rớt về Tier A rác.
- **Siết out-of-book** (`docs/pilot/MULTISUBJECT_SCALE_2026_06_14.md`): nâng floor `bs>=0.52→0.60` + margin `0.03→0.04`. Kết quả: out-of-book guard 34.8%→63.8%, chitchat 87.9%→97.1%, cruft vẫn 0. Backup canary `.bak_pre_oobfix_2026_06_14`.

> **Gate hiện hành (hợp nhất, theo canonical task brief)**: `bs >= 0.50 AND (margin >= 0.04 OR bs >= 0.60)`.
> Nghĩa: chấp nhận card nếu best-score đủ cao **và** (đủ tách top1/top2 **hoặc** best-score rất cao). Không thoả → trả `none`/`noncard` (từ chối an toàn).

Hệ quả thiết kế: gate này **bảo vệ "sạch nguồn" + "từ chối ngoài bài"**, nhưng đánh đổi bằng việc `content_only` (câu mô tả không neo) thường bị từ chối — đó là lý do `content_only` anchor 22–43% ở các quyển yếu, **không** phải lỗi production (prod luôn có `current_lesson`).

## 4. Intent / mode (độc lập với anchor)

Sau khi neo bài, chọn `tier` (mode):
- **Intent = embedding classifier** (BGE so query với anchor-phrase {recite / practice / explain}, margin ~0.035; regex giữ fast-path). Không cần Gemma ở serve path (+~40ms nếu có).
- Tier card: `lesson_card` (giảng) · `lesson_practice` (luyện) · `lesson_recite` (đọc thuộc) · `A_concept` (Tier A-concept hit) · `none` (từ chối).

`mode_acc` trong backtest = anchor đúng **và** tier == expected_mode.

## 5. Cách scorer chấm anchor (quan trọng cho phân tích gap)

`backtest_book.py` L117-119, L139:
```python
def norm(x):
    x=(x or "").replace("đ","d").replace("Đ","D"); x=unicodedata.normalize("NFD",x)
    return "".join(c for c in x if unicodedata.category(c)!="Mn").lower().strip()
...
a = (norm(work)==norm(ew))   # EXACT match sau khi fold dấu + lowercase
```

> **Hệ quả then chốt**: anchor = **so khớp tuyệt đối chuỗi work_name** (sau fold dấu). Mọi khác biệt suffix / dấu gạch ngang / giới từ giữa `expected_work` (ground-truth trong DB) và `work_name` server trả về ⇒ **FAIL dù neo đúng bài**. Đây là gốc rễ một phần lớn gap Lịch sử (xem `history-work-name-normalization.md`) — không phải retrieval chọn sai bài, mà là tên không trùng chuỗi.

## 6. Đường production thật vs đường backtest "yếu"

- **current_lesson dimension**: Toán 4/5/6 KNTT, Lịch sử 6 KNTT = **anchor 100%** (76.8% riêng toan 8 CTST t1 — xem ghi chú). → đường thật chạy ổn.
- **content_only / trang_* dimension**: nơi anchor tụt (22–55%). Đây là ca thiếu/mờ anchor, một phần là từ chối-đúng.
- Vì baseline tổng "anchor 97%" trộn cả các dimension này theo tỉ trọng từng quyển, **quyển Toán tiểu học tụt** chủ yếu vì tỉ trọng `content_only`/`trang_*` cao + tên bài/khái niệm khó match, **không phải** vì đường `current_lesson` hỏng.

## Tham chiếu mã
- `rag_edu/scripts/schema_v3_2026_06/patch_tc_canary.py` — grade propagation + `query_concept_exact`.
- `rag_edu/scripts/schema_v3_2026_06/patch_tc2_concept_match.py` — word-overlap concept match.
- `rag_edu/scripts/schema_v3_2026_06/backtest_book.py` — scorer `norm()` exact-match (L117-141).
- `rag_edu/scripts/schema_v3_2026_06/backfill_worknorm.py`, `v_a_work_name.py` — `work_name_norm` / `fold()`.
