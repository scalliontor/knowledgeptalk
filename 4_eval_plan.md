# Chiến lược thử nghiệm & Evaluation

## Nguyên tắc: Đo lường trước khi build

Đừng build xong rồi mới đánh giá. Mỗi bước phải có metric rõ ràng. Nếu không đo được, không biết có tốt lên không.

## Phase 1: Crawl Quality (Tuần 1-2)

### Metrics cần đo

| Metric | Cách đo | Threshold |
|--------|---------|-----------|
| **Coverage** | Số bài crawl được / Tổng bài ước tính | >80% |
| **Extraction accuracy** | Manual check 50 random samples | >90% content chính xác |
| **Classification accuracy** | Label 100 samples thủ công, so với LLM classifier | >85% |
| **Duplicate rate** | % bài có cosine similarity > 0.9 với bài khác | Giảm dần qua dedup |
| **Crawl success rate** | Requests thành công / Total | >95% |

### Cách thực hiện

1. Crawl 500 bài đầu tiên (lớp 1-5, bộ KNTT)
2. **Manual audit 50 bài random**:
   - Content extract có đầy đủ không? (không bị cắt cụt)
   - Không có nav/footer/ads chen vào?
   - Title đúng không?
3. Ghi vào spreadsheet cột: `url | quality_ok | issue`
4. Tính tỉ lệ, nếu <90% → fix extraction logic

### Red flags cần watch

- Trang bị rate limit (HTTP 429) → giảm concurrency, tăng delay
- Trang redirect loop → check logic handle redirects
- Content có `<script>` leak ra → trafilatura config chưa đúng
- Bài lớp 1 ngắn bất thường (<20 từ) → bình thường, không phải lỗi

## Phase 2: RAG Retrieval Quality (Tuần 3-4)

### Build eval set TRƯỚC, không phải sau

Đây là step hầu hết dev bỏ qua, dẫn đến "tuning mù".

**200 câu hỏi thật từ trẻ em**, phân phối:

| Loại câu hỏi | Số lượng | Ví dụ |
|--------------|----------|-------|
| Tra cứu bài đọc cụ thể | 40 | "Bài Lượm có câu gì?" |
| Hỏi về nhân vật/nội dung | 40 | "Bà tiên trong truyện Tấm Cám làm gì?" |
| Khái niệm ngữ pháp | 30 | "Từ ghép là gì hả chị?" |
| Hỏi chính tả | 20 | "Viết 'l' hay 'n' trong từ 'năm'?" |
| Giúp viết văn | 40 | "Em không biết tả con mèo, giúp em" |
| Hỏi lung tung (trò chuyện) | 30 | "Chị ơi hôm nay là thứ mấy?" |

**Cách collect**:
- Ghi âm trẻ thật (con bạn, con đồng nghiệp) 1 giờ → 20-30 câu
- Fake remaining bằng LLM (prompt "giả làm trẻ lớp 3 hỏi gia sư")
- Review bởi giáo viên tiểu học

### Retrieval metrics

Cho mỗi câu hỏi, gán nhãn:
- `expected_collection`: collection nào nên retrieve (sgk_readings? concepts? outlines?)
- `expected_kb_ids`: các KB entry nào là "đúng đáp án"

Đo:
- **Recall@5**: trong top 5 retrieved, có chứa expected KB không? (target >0.85)
- **Precision@5**: trong top 5, có bao nhiêu relevant? (target >0.6)
- **MRR (Mean Reciprocal Rank)**: rank trung bình của answer đúng (target: top 1-2)
- **Collection routing accuracy**: classifier có chọn đúng collection không? (target >90%)

### Tool để đo

- [RAGAS](https://github.com/explodinggradients/ragas) - framework eval RAG
- Hoặc tự viết scripts đơn giản với pandas

## Phase 3: End-to-end Conversation Quality (Tuần 5-6)

Đây là phần khó đo nhất, cần kết hợp automated + human.

### Automated metrics

| Metric | Cách đo |
|--------|---------|
| **Answer faithfulness** | LLM judge: câu trả lời có bám vào retrieved context không? |
| **Answer relevance** | LLM judge: có trả lời đúng câu hỏi không? |
| **Response length** | Mean tokens; cho voice chat: 20-60 tokens là tốt |
| **Latency** | P50, P95 end-to-end |
| **Hallucination rate** | % câu trả lời có fact sai (cần KB làm ground truth) |

### Human evaluation (quan trọng hơn automated)

Thuê 2-3 giáo viên tiểu học + 5-10 phụ huynh đánh giá.

**Rubric** (thang điểm 1-5):
- **Correctness**: thông tin có đúng không?
- **Age-appropriate**: có phù hợp trẻ [lớp X] không?
- **Pedagogy**: có dạy đúng cách không? (không giải thay, không rập khuôn)
- **Warmth**: có giọng điệu thân thiện không?
- **Voice-friendliness**: đọc to lên có tự nhiên không? (không list, không markdown)

Target: điểm trung bình >4.0/5 cho mọi tiêu chí.

## Phase 4: A/B Test - So sánh RAG vs Non-RAG baseline

Đây là test **sống còn** - để biết RAG có thực sự giúp ích không.

### Setup

- **Arm A**: LLM thuần (Claude Sonnet 4.6 hoặc GPT-4) với system prompt về persona tiểu học. Không RAG.
- **Arm B**: Same LLM + RAG pipeline của bạn

### Test cùng 200 câu eval set

Blind review bởi giáo viên: so sánh câu trả lời của A vs B, chọn cái tốt hơn.

**Kịch bản có thể xảy ra:**

| Kết quả | Ý nghĩa | Hành động |
|---------|---------|-----------|
| B thắng >70% | RAG có giá trị rõ ràng | Tiếp tục invest |
| B thắng 50-70% | RAG có chút giá trị | Xem lại architecture, có lẽ chỉ RAG cho 1 số loại query |
| B thắng <50% | RAG đang hại hơn giúp | Dừng, suy nghĩ lại (có thể cần hybrid approach) |

**Đây là sự thật khó nghe:** với tiểu học và LLM lớn, kết quả rất có thể là 50-70%. Đừng build RAG to đùng rồi discover điều này sau.

### Breakdown theo loại câu hỏi

Có thể RAG thắng ở "tra cứu bài cụ thể" nhưng thua ở "trò chuyện chung". Đây là insight quan trọng để quyết định **khi nào cần RAG**:

```
Query classifier:
  if query loại "tra cứu factual" → dùng RAG
  else if query loại "trò chuyện / động viên" → LLM thuần
  else if query loại "viết văn" → dàn ý từ KB + LLM generate
```

## Phase 5: Production Monitoring (sau launch)

Sau khi có user thật:

- **Satisfaction**: thumbs up/down mỗi response
- **Session length**: trẻ có quay lại không?
- **Drop-off points**: ở câu hỏi nào trẻ bỏ đi?
- **Human escalation rate**: bao nhiêu % user cần phụ huynh vào cứu?

Setup logging ngay từ đầu. Dùng tools như LangSmith, Langfuse, hoặc tự build.

## Checklist trước khi scale

Trước khi crawl thêm trang / lớp / môn, phải có:

- [ ] 200 câu eval set đã label
- [ ] Retrieval recall@5 > 0.80 trên eval set
- [ ] A/B test cho thấy RAG có value
- [ ] Human evaluation >4.0/5
- [ ] Latency P95 < 2 giây (cho text; voice có thể khác)
- [ ] Monitoring dashboard chạy ngon

Nếu chưa đủ → **không scale**. Fix quality trước.

## Cảnh báo các pitfalls phổ biến

1. **"Crawl càng nhiều càng tốt"** - SAI. 1000 bài chất lượng > 10000 bài tạp.

2. **"Tune retrieval trước, eval sau"** - SAI. Không có eval set thì tune là mù.

3. **"Test với câu hỏi dev tự nghĩ"** - SAI. Dev không nghĩ như trẻ em.

4. **"Một metric đẹp là đủ"** - SAI. Recall cao nhưng user không thích - failure.

5. **"Launch khi xong RAG"** - SAI. Launch MVP không RAG trước, thấy real user behavior, rồi quyết định chỗ nào cần RAG.

## Tóm tắt timeline đề xuất

```
Tuần 1:     Design + Eval set (quan trọng nhất, đừng skip)
Tuần 2-3:   Crawl loigiaihay lớp 1-5 KNTT
Tuần 4:     Clean + Classify + Dedup
Tuần 5:     Index vào Qdrant, build retrieval pipeline
Tuần 6:     Measure retrieval metrics, iterate
Tuần 7:     Build end-to-end với LLM, measure conversation quality
Tuần 8:     A/B test vs baseline, quyết định scale hay pivot
```
