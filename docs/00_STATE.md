# 00 — TRẠNG THÁI DỰ ÁN (2026-06-05)

> Ảnh chụp trạng thái để bất kỳ ai (hoặc session sau) nắm ngay "ta đang ở đâu". Vận hành: [RUNBOOK.md](RUNBOOK.md). Quyết định: [design/kg-schema-v3.md](design/kg-schema-v3.md).

## Tóm tắt 1 dòng
RAG voice-tutor K-9. **5 môn đã lên schema v3** trong Neo4j (concept layer + structured-first). **Prod :8888 đang UP (code CŨ)**. **Code MỚI (Gemma-free + Tier A, ~50ms thay vì 2.7s) đã sẵn ở canary, chờ merge sang prod** (giữ endpoint moderation).

## Services
| | Port | Trạng thái |
|---|---|---|
| prod ptalk_rag | 8888 | ✅ UP — code CŨ (Gemma router mọi query → 2-3s, chưa có Tier A concept) |
| canary | 8889 | ⚪ down — chứa code MỚI (chưa deploy) |
| edu_neo4j | 7688 | ✅ |
| Gemma vLLM | 8080 | ✅ (chỉ còn dùng cho compose answer, KHÔNG cho retrieve sau khi merge) |

## Data (Neo4j edu) — 5 môn K-9 schema v3
| Môn | Lớp | Concepts | Eval (structured / concept) |
|---|---|---|---|
| Toán | 1-9 | 677 + 6 strand | bài/trang 98-100% · concept 80% |
| Ngữ văn | 6-9 | 418 tác phẩm | tác phẩm/section 100% · recite (68 works có verbatim) |
| Xã hội (Sử/Địa/GDCD) | 6-9 | 421 | bài 100% · kiến thức 93-100% |
| KHTN (+Lý/Hóa/Sinh) | 5-10 | 379 | bài/trang 100% · kiến thức 94% |
| Tiếng Việt | 1-5 | 1988 | bài/trang 97-100% · concept 100% |

Tổng ~3.900 Concept · ~5.200 COVERS · **cross-grade leak = 0** · +37 bài thơ verbatim mới crawl. Mọi mutation actor-tagged reversible.

## Code mới (canary) — 6 thay đổi đã làm + verify
1. **Gemma-free retrieve** (regex router 93% vs Gemma 53% subject, 0.1ms vs 2s)
2. **Tier A** structured (bài/trang) + concept (chủ đề) — return trước router
3. **_fold self-contained** (đ→d+NFD) — fix bug unidecode no-op làm concept tier CHẾT
4. **recite hardened** (18/18 pos, 16/16 neg, loại "đọc hiểu")
5. **router fixes** (LICHSU bỏ generic, VANHOC→Văn, greeting regex, MATH +tỉ lệ)
6. **subject từ profile**

## Việc CÒN LẠI
1. ⛔ **Merge code mới → prod** (ghép moderation endpoint vào canary → set port 8888 → deploy bằng SCRIPT method ở [RUNBOOK §2](RUNBOOK.md)). Đây là thứ kéo latency 2.7s → 50ms + hồi sinh concept tier.
2. Verify live sau merge (health + 4 endpoint + concept query + recite + latency).
3. Crawl thêm thơ recite (tăng coverage tiếp).
4. (User) Update Dashboard `/kg-browse` theo [design/dashboard-kg-viewer-v2.md](design/dashboard-kg-viewer-v2.md).
5. Companion layer (Student/Session/PREREQ traversal).

## Bài học lớn của session
- **Launch rag_server PHẢI dùng script file + nohup** (inline ssh fail) — xem RUNBOOK §2.
- **Template eval đánh giá CAO hơn thực tế** — phải dùng Gemma4 natural-language làm gate.
- **Gemma router không cần** — regex tốt hơn + nhanh hơn cho retrieve.
- **Canary thiếu endpoint của prod** — không copy thẳng, phải merge.
- **đ→d fold** là bug kinh điển (unicodedata không tách đ).

Git: branch `docs/kg-schema-v3-knowledge` (chưa push). Memory bank `master_state_2026_06_05` = bản canonical đầy đủ nhất.
