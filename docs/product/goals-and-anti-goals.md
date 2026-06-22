# Goals & Anti-Goals — Knowledge PTalk LÀ gì / KHÔNG phải gì

> Nguồn: [project_state/2026-06-22-canonical.md](../project_state/2026-06-22-canonical.md) (north star + invariant + gap). Dùng bảng này để đặt kỳ vọng đúng và bắt scope-creep sớm.

## Bảng LÀ vs KHÔNG phải

| Chiều | ✅ **LÀ** | ❌ **KHÔNG phải** |
|---|---|---|
| **Bản chất** | Bạn đồng hành học **một bài SGK cụ thể** đang mở. | Trợ lý hỏi-đáp tổng quát / chatbot kiến thức mở. |
| **Đầu vào** | Hồ sơ + ngữ cảnh: `lop`, `bo_sach`, `subject`, `current_lesson` (hoặc `trang`+`tap`). | Chỉ một câu hỏi trần, không ngữ cảnh bài. |
| **Cách neo** | Structured-first: `current_lesson` → tên bài → `trang`+`tập` → mới tới content-vector. | Vector search toàn corpus là đường chính. |
| **Phạm vi đáp** | Đúng **môn + lớp + bộ sách + tập** đang học. | Trộn tập 1/2, trộn bộ sách, trộn lớp. |
| **3 việc cốt lõi** | **Giảng** lại bài, cho **đọc thuộc** (nguyên văn), **luyện tập có dẫn dắt** (câu hỏi + gợi ý + đáp án ẩn). | Giải hộ bài tập về nhà / đưa đáp án trần không sư phạm. |
| **Nguồn nội dung** | Sạch — nghe như bài giảng. | Leak "vietjack", "xem lời giải", "video giải", "cô giáo VietJack". |
| **Khi ngoài bài** | **Từ chối an toàn** ("cái này không trong bài hôm nay"). | Đoán bừa / hallucinate để luôn có câu trả lời. |
| **Độ trễ** | Serve path **Gemma-free**, P95 ~200–370 ms. | LLM trong đường nóng (2–3 s). |
| **Mô hình** | Tận dụng stack sẵn (BGE-m3 embed, Neo4j, regex/embedding router). | Thêm model mới vào serve path. |
| **Chunk** | Doc-level (~3–15K chars), điều hướng granularity qua metadata + edge. | Split nhỏ dưới mức bài/section. |
| **Đọc thuộc** | Verbatim từ `LiteratureText` đã validate, **rights-gated**. | Đọc "thuộc" bằng cách paraphrase / chế lại. |
| **Companion chiều sâu** | Học sinh xin "giảng kỹ" (chi_tiet) / "tóm tắt nhanh" (sieu_ngan) → chọn variant. | Nhân bản concept cho mỗi độ sâu. |

## Anti-goals (việc cố ý KHÔNG làm — refuted/deferred)

- ❌ **Không** học prerequisite từ telemetry adjacency — seed từ chương trình (GDPT 2018).
- ❌ **Không** gọi LLM tag mỗi lượt hội thoại trong serve path.
- ❌ **Không** đưa PREREQ DAG / mastery vào Văn (evidence chỉ vững cho Toán; mastery là Phase 3 cần telemetry chưa có).
- ❌ **Không** refactor mù single-file runtime thành package rồi tưởng đã deploy (`/packages/*` là **đề xuất tổ chức**, cần migration plan riêng).
- ❌ **Không** coi `content_only` thấp (25–47%) là gap — đa số là **từ chối an toàn** (không có neo → không đoán); production gần như không gặp vì luôn có `current_lesson`.

## Invariant không được phá (mọi PR)

Từ canonical — vi phạm bất kỳ dòng nào = chặn merge:

| Invariant | Không được làm hỏng |
|---|---|
| Structured-first routing | `current_lesson` → tên bài → trang+tập → content-vector |
| Scope chặt | môn + lớp + bộ sách + **tập** |
| Không trùng tập 1/2 | page reset xử lý theo `tap_no` |
| Gemma-free serve path | không đưa LLM vào đường latency-critical |
| Sạch nguồn | không leak vietjack / lời giải / cô-giáo-VietJack |
| Refuse ngoài bài | không hallucinate khi ngoài scope |
| Backtest là gate | không merge nếu không có report mới + diff |

## Gap thật (đang LÀ nhưng chưa đủ tốt — ≠ anti-goal)

Đây là điểm yếu thật cần cải thiện, không phải ranh giới phạm vi:
1. **Toán tiểu học lớp 4–6 anchoring 82–86%** (nghi tên bài dài/định dạng lạ) — điểm yếu số 1.
2. **Lịch sử 95.5%** (nghi `work_name_norm` lệch ở vài bài: số La Mã, gạch ngang, năm).
3. **Chưa promote prod :8888** — prod vẫn code cũ (chưa có companion).
4. **Client gửi `{}`** — anchor 97% chỉ đạt khi app gửi `current_lesson`/`trang`+`tap`; cần contract + integration.

> Lưu ý đính chính: "204 cruft" cũ là **false-positive** do keyword test `"giáo viên"` bắt nhầm từ vựng hợp lệ. Rác nguồn THẬT = 0 (verify trực tiếp Neo4j toàn 1852 chunk). Goal "sạch nguồn" ĐẠT.

---
Liên quan: [north-star.md](north-star.md) · [lesson-card-model.md](lesson-card-model.md) · [canonical](../project_state/2026-06-22-canonical.md)
