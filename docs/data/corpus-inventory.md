# Corpus Inventory — Knowledge PTalk (65 quyển / 1852 bài)

> **Vai trò**: Corpus / Data-Quality. **Nguồn dẫn xuất**: `reports/backtest/2026-06-17_full-sweep/*.json` (81 file backtest, field `book` + `lessons` + `by_dimension`), đối chiếu tên file `backtest_<subject>_<grade>_<bookset>_<tap>.json`.
> **Ràng buộc**: tài liệu MỚI, chỉ suy ra từ artifact local — **không** SSH, **không** đọc Neo4j vòng này. Số liệu khớp `docs/project_state/2026-06-22-canonical.md` (65 quyển / 1852 bài / 6 môn).
> **Ngày**: 2026-06-22.

## 0. Quy ước đếm (quan trọng — tránh đếm trùng)

Có **81 file backtest** nhưng chỉ **65 quyển vật lý**. Lý do: một số quyển được chạy ở **2 dạng scope**:

- `tNone` = chạy **cả quyển** (không tách tập). Dùng cho môn 1-tập (Sử/Địa/GDCD/KHTN) và cho một vài quyển Toán tiểu học.
- `t1` / `t2` = chạy **theo từng tập** (volume-aware), kiểm tra chống trùng tập 1/2.

**Quy tắc rollup về 65 quyển vật lý** (đã verify khớp 1852 bài):

```
quyển vật lý  = (subject, grade, book_set)
lessons       = lessons của file tNone nếu có  (whole-book)
                ngược lại = Σ(t1 + t2)          (quyển 2 tập, không có whole-book run)
```

⚠️ **Các file `tNone` của Toán 4/5/6 KNTT là RE-RUN whole-book chồng lấn** với split — KHÔNG cộng dồn vào split. Whole-book `tNone` có anchor thấp hơn split (75–79% vs 85–97%) vì chạy không có volume scope → đó là **chế độ chẩn đoán**, không phải quyển riêng.

Tổng kiểm: 65 quyển vật lý → **1852 bài** (verified).

## 1. Tổng theo môn

| Môn (subject_code) | Số quyển | Số bài | Anchor headline (range) | current_lesson (production path) |
|---|---|---|---|---|
| toan | 13 | 537 | 75.1–96.7 | ~98–100 (trừ toan 8 CTST t1 = 76.8) |
| ngu_van | 4 | 127 | 79.1–86.4 | ~98.9–100 |
| khtn | 12 | 542 | 81.4–89.2 | 95.5–100 |
| lich_su | 12 | 253 | 73.2–87.1 | 79.0–100 (g9 CTST/KNTT thấp) |
| dia_li | 12 | 246 | 77.4–91.9 | 97.3–100 |
| gdcd | 12 | 147 | 87.5–94.7 | 100 |
| **TỔNG** | **65** | **1852** | — | — |

> **Cảnh báo đọc số**: `anchor` headline (cột 4) gộp cả dimension `content_only` (câu hỏi KHÔNG có `current_lesson` → phần lớn là **từ chối an toàn**). Cột `current_lesson` (cột 5) là **đường production thật** (app gửi neo bài/trang). Headline thấp ở Toán tiểu học (75–80%) chủ yếu do `content_only`, KHÔNG phải production path tệ — xem §4.

## 2. Bảng 65 quyển

Cột `anchor` = `anchor_acc` headline; cột `cl%` = anchor% của dimension `current_lesson` (đường production). Quyển 2 tập ghi cả hai tập.

| Môn | Lớp | Bộ sách | Tập (run) | Bài | anchor | cl% | Cờ |
|---|---|---|---|---|---|---|---|
| dia_li | 6 | CD | tNone | 26 | 86.6 | 100.0 | |
| dia_li | 6 | CTST | tNone | 24 | 89.4 | 100.0 | |
| dia_li | 6 | KNTT | tNone | 30 | 87.1 | 100.0 | |
| dia_li | 7 | CD | tNone | 21 | 81.2 | 100.0 | |
| dia_li | 7 | CTST | tNone | 22 | 82.6 | 100.0 | |
| dia_li | 7 | KNTT | tNone | 19 | 83.8 | 100.0 | |
| dia_li | 8 | CD | tNone | 12 | 90.3 | 100.0 | |
| dia_li | 8 | CTST | tNone | 15 | 91.8 | 100.0 | |
| dia_li | 8 | KNTT | tNone | 12 | 91.9 | 100.0 | |
| dia_li | 9 | CD | tNone | 20 | 83.3 | 100.0 | |
| dia_li | 9 | CTST | tNone | 23 | 77.4 | 97.3 | headline thấp |
| dia_li | 9 | KNTT | tNone | 22 | 82.8 | 100.0 | |
| gdcd | 6 | CD | tNone | 12 | 93.6 | 100.0 | cruft FP=19 |
| gdcd | 6 | CTST | tNone | 12 | 90.8 | 100.0 | cruft FP=17 |
| gdcd | 6 | KNTT | tNone | 12 | 91.4 | 100.0 | |
| gdcd | 7 | CD | tNone | 12 | 92.2 | 100.0 | cruft FP=19 |
| gdcd | 7 | CTST | tNone | 12 | 90.6 | 100.0 | cruft FP=34 |
| gdcd | 7 | KNTT | tNone | 27 | 87.5 | 100.0 | cruft FP=11 |
| gdcd | 8 | CD | tNone | 10 | 91.7 | 100.0 | |
| gdcd | 8 | CTST | tNone | 10 | 93.3 | 100.0 | |
| gdcd | 8 | KNTT | tNone | 10 | 91.0 | 100.0 | cruft FP=10 |
| gdcd | 9 | CD | tNone | 10 | 94.7 | 100.0 | |
| gdcd | 9 | CTST | tNone | 10 | 94.7 | 100.0 | cruft FP=36 |
| gdcd | 9 | KNTT | tNone | 10 | 91.3 | 100.0 | |
| khtn | 6 | CD | tNone | 33 | 88.5 | 95.8 | cruft FP=4 |
| khtn | 6 | CTST | tNone | 44 | 82.6 | 97.4 | cruft FP=3 |
| khtn | 6 | KNTT | tNone | 71 | 81.4 | 97.4 | **quyển lớn nhất**; cruft FP=13 |
| khtn | 7 | CD | tNone | 34 | 87.8 | 95.8 | |
| khtn | 7 | CTST | tNone | 39 | 89.2 | 98.8 | |
| khtn | 7 | KNTT | tNone | 42 | 87.3 | 100.0 | |
| khtn | 8 | CD | tNone | 43 | 87.1 | 100.0 | |
| khtn | 8 | CTST | tNone | 51 | 87.3 | 95.5 | |
| khtn | 8 | KNTT | tNone | 47 | 88.7 | 100.0 | |
| khtn | 9 | CD | tNone | 42 | 86.4 | 100.0 | |
| khtn | 9 | CTST | tNone | 45 | 84.9 | 100.0 | |
| khtn | 9 | KNTT | tNone | 51 | 86.4 | 100.0 | |
| lich_su | 6 | CD | tNone | 20 | 83.3 | 98.6 | |
| lich_su | 6 | CTST | tNone | 27 | 79.8 | 100.0 | |
| lich_su | 6 | KNTT | tNone | 25 | 80.0 | 100.0 | |
| lich_su | 7 | CD | tNone | 21 | 79.1 | 95.6 | |
| lich_su | 7 | CTST | tNone | 21 | 81.2 | 100.0 | |
| lich_su | 7 | KNTT | tNone | 18 | 79.1 | 100.0 | |
| lich_su | 8 | CD | tNone | 16 | 83.8 | 100.0 | |
| lich_su | 8 | CTST | tNone | 22 | 84.7 | 100.0 | |
| lich_su | 8 | KNTT | tNone | 18 | 83.1 | 100.0 | |
| lich_su | 9 | CD | tNone | 21 | 87.1 | 100.0 | |
| lich_su | 9 | CTST | tNone | 23 | **73.2** | **79.0** | ⚠️ **production-path weak #1** |
| lich_su | 9 | KNTT | tNone | 21 | 82.4 | 88.2 | ⚠️ production-path weak |
| ngu_van | 6 | CTST | t1+t2 | 35 | 80.9 / 84.2 | 98.9 / 100.0 | 2 tập |
| ngu_van | 7 | CTST | t1+t2 | 35 | 82.6 / 82.4 | 98.9 / 100.0 | 2 tập |
| ngu_van | 8 | CTST | t1+t2 | 44 | 80.2 / 79.1 | 98.9 / 98.9 | 2 tập; t2 cruft FP=27 |
| ngu_van | 9 | CTST | t2 | 13 | 86.4 | 100.0 | chỉ t2 (pilot gốc) |
| toan | 4 | CTST | tNone | 63 | **75.1** | 100.0 | headline thấp (content_only) |
| toan | 5 | CTST | tNone | 80 | **76.5** | 100.0 | **quyển nhiều bài**; headline thấp |
| toan | 6 | CTST | t2 | 24 | 90.8 | 100.0 | chỉ t2 trong sweep |
| toan | 6 | KNTT | tNone | 60 | 79.1 | 100.0 | headline thấp (content_only) |
| toan | 7 | CD | t1+t2 | 42 | 89.9 / 85.4 | 100.0 / 100.0 | 2 tập |
| toan | 7 | CTST | t1+t2 | 35 | 88.9 / 88.2 | 100.0 / 100.0 | 2 tập |
| toan | 7 | KNTT | t1+t2 | 37 | 88.9 / 89.2 | 100.0 / 100.0 | 2 tập |
| toan | 8 | CD | t1+t2 | 35 | 79.1 / 86.1 | 100.0 / 100.0 | 2 tập; t1 headline thấp |
| toan | 8 | CTST | t1+t2 | 32 | 78.6 / 87.8 | **76.8** / 100.0 | ⚠️ **t1 production-path weak** |
| toan | 8 | KNTT | t1+t2 | 39 | 83.3 / 87.5 | 98.5 / 100.0 | 2 tập |
| toan | 9 | CD | t1+t2 | 30 | 88.2 / 86.2 | 100.0 / 100.0 | 2 tập |
| toan | 9 | CTST | t1+t2 | 28 | 87.3 / 87.2 | 100.0 / 100.0 | 2 tập |
| toan | 9 | KNTT | t1+t2 | 32 | 87.8 / 85.6 | 100.0 / 100.0 | 2 tập |

## 3. Quyển bất thường (cần để mắt)

- **toan 6 KNTT tập 2 = 4 bài** (file `backtest_toan_6_KNTT_t2.json`, anchor 96.7). Trong rollup whole-book ta dùng `tNone` (60 bài) nên KHÔNG double-count, nhưng **4 bài t2 quá ít** → nghi tập 2 bị thiếu phần lớn bài, hoặc tap-signal trong `text` ("Tập 2") bắt sai ở builder (`build_book_generic.py` đếm `t1` vs `t2` từ `k.text CONTAINS 'Tập 2'`). **Cần verify coverage tập 2 toan 6 KNTT** (xem checklist Q-COV).
- **toan 5 CTST = 80 bài / toan 4 CTST = 63 bài / toan 6 KNTT = 60 bài** (whole-book): nhiều bài + headline anchor thấp nhất (75–79%). Đây là điểm yếu thật số 1 theo canonical — nhưng phân rã cho thấy `current_lesson`=100%, headline kéo bởi `content_only` (xem §4).
- **khtn 6 KNTT = 71 bài** (quyển lớn nhất corpus). Cruft FP=13 (false-positive "giáo viên", không phải rác thật).
- **ngu_van 9 CTST chỉ có tập 2** trong sweep (13 bài) — tập 1 chưa được build/test (pilot gốc chỉ làm t2). **Gap coverage**: ngu_van 9 t1 vắng.

## 4. Quyển 2 tập (rủi ro trùng tập 1/2)

Tổng cộng **13 quyển vật lý 2 tập** (toan g7–g9 mọi bộ, toan 6 CTST/KNTT, ngu_van g6–g8 CTST). Page-number reset giữa tập 1 và tập 2 → nếu anchor theo `trang` mà không scope `tap_no` thì trang 50 tập 1 đụng trang 50 tập 2.

- **Bằng chứng phân tách tập OK** (canonical): toan 8 KNTT **t1=96.4 / t2=98.8** (đây là `current_lesson` path) → volume separation hoạt động.
- **Cờ cần xác minh**: toan 6 KNTT t2 chỉ 4 bài (coverage, không phải collision); toan 8 CTST t1 production-path 76.8% (xem §2). Không thấy dấu hiệu trang-collision trong dimension `trang_query`/`trang_profile` (đều ~93–100%).
- Checklist Cypher để kiểm trùng tập sau: xem `data-quality-checklist.md` Q-DUP-VOL.

## 5. Coverage gap đã biết (từ audit, chưa có trong sweep)

Audit `docs/audit/rag_subject_audit_2026_06_14.md` ghi các môn **ngoài 6 môn sweep** vẫn nằm trong Neo4j edu nhưng CHƯA có companion Lesson Card và CHƯA vào backtest:

- tieng_viet (4898 chunk), tieng_anh (1166), sinh_hoc (1050), hoa_hoc (684), vat_li (579) — chỉ ở RAG nền (Tier A + vector), chưa build :Lesson.
- Coverage trống cụ thể: **"định luật Ôm" (Vật lí 9) → KHÔNG có data**.
- **Văn / Tiếng Việt cần builder CURATE TAY** (per MEMORY multisubject scale) — generic driver không đủ cho 2 môn này.

---
Liên quan: `docs/project_state/2026-06-22-canonical.md` · `docs/data/data-quality-checklist.md` · `docs/data/neo4j-schema-v3.md` · `reports/backtest/2026-06-17_full-sweep/`
