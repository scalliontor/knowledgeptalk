# Research — Graph RAG tổ chức dữ liệu cho chatbot đồng hành học tập

> **Ngày**: 2026-06-03 · **Phương pháp**: deep-research harness (107 agents, 5 angles, 25 primary sources, 108 claims → 25 verify → **17 confirmed / 8 refuted**) · **Run**: `wf_ba9806ac-b34`
> **Câu hỏi**: Tổ chức KG document-level (Neo4j) cho voice tutor K-12 VN — Toán vs Văn khác nhau thế nào? Mode = **đồng hành học bài cụ thể** (không phải Q&A mở), structured-first, KHÔNG deploy model mới.

Doc này là **evidence base**. Quyết định schema cụ thể ở [../design/kg-schema-v3.md](../design/kg-schema-v3.md).

---

## TL;DR — 1 pattern thống trị

> **Tách lớp Concept/Skill ra khỏi lớp Document/Chunk** thành **node type riêng**, nối bằng **explicit edge** `(chunk)-[:COVERS]->(concept)` — KHÔNG nhúng concept làm property của chunk.

Pattern này xuất hiện đồng thời ở **cả** graph-RAG libraries (Neo4j GraphRAG, HippoRAG, Microsoft GraphRAG) **lẫn** intelligent tutoring systems (TrueLearn, ALEKS/KST, Q-matrix ITS). Đây là quyết định nền tảng cho cả Toán và Văn.

---

## 9 findings (đã verify adversarial ≥2/3 vote)

### F1 — DECOUPLE concept khỏi chunk (HIGH, 4 nguồn 3-0)

Concept/Skill (Knowledge Component) phải là **node type tách biệt**, không phải property trong chunk.

- **Neo4j GraphRAG**: tách "lexical graph" (Document + Chunk nodes) khỏi "entity graph" (entities là node type riêng).
- **HippoRAG**: lưu 3 embedding store riêng (chunk / entity / fact) ở namespace khác nhau.
- **TrueLearn (AAAI 2020)**: mỗi trang Wikipedia = 1 KC (7,948–10,524 KC trên ~3,884 lecture); resource chỉ *link* vào top-k KC; mastery sống ở **lớp KC** chứ không ở resource.
- **ITS prereq paper (arXiv 2402.01672)**: tách "KC-exercise graph" khỏi "Knowledge Structure DAG" (prereq giữa KC).

> ⚠️ Nuance: "decoupled" = **node type riêng nhưng VẪN nối topologically** (entity → chunk qua `FROM_CHUNK`/`HAS_ENTITY`). Không phải subgraph rời rạc. Đúng pattern `(chunk)-[:COVERS]->(concept)` ta cần.

Nguồn: [neo4j.com/docs/neo4j-graphrag-python](https://neo4j.com/docs/neo4j-graphrag-python/current/user_guide_kg_builder.html) · [github.com/osu-nlp-group/hipporag](https://github.com/osu-nlp-group/hipporag) · [arxiv 1911.09471](https://arxiv.org/pdf/1911.09471) · [arxiv 2402.01672](https://arxiv.org/pdf/2402.01672)

### F2 — EXPLICIT named edges, không phải metadata property (HIGH, 2 nguồn 3-0)

Nối doc chunk vào backbone bằng **edge có tên thật** trong Neo4j, không chỉ filter trên property.

- Neo4j GraphRAG tạo relationship thật ở code level (`create_chunk_to_document_rel()`, `create_next_chunk_relationship()` → `FROM_DOCUMENT`, `NEXT_CHUNK`, bật mặc định).
- Microsoft GraphRAG: provenance qua `text_unit_ids` — entity/relationship/claim reference TextUnit gốc → traceback "concept → source text".

→ Với PTalk: **giữ hierarchy edge sẵn có + THÊM concept layer reachable bằng traversal**, thay vì chỉ filter chunk metadata. (Validate lựa chọn explicit-edge over Parent-Document-via-metadata.)

Nguồn: [neo4j GraphRAG](https://neo4j.com/docs/neo4j-graphrag-python/current/user_guide_kg_builder.html) · [microsoft.github.io/graphrag](https://microsoft.github.io/graphrag/index/default_dataflow/)

### F3 — Retrieve GRAPH-FIRST rồi project xuống document (HIGH, 3-0)

HippoRAG: (a) link query entity → KG node bằng similarity; (b) chạy **Personalized PageRank** trên concept graph; (c) nhân node-probability với ma trận node×passage để rank passage.

→ Concept-to-document link là **mapping/edge**, KHÔNG phải concept nhúng trong chunk. Bổ trợ cho Cypher-exact-then-vector của PTalk: có thể thêm path "concept graph → project to chunks".

> ⚠️ "canonical" overreach: ma trận P là design riêng của HippoRAG; **HippoRAG 2 (2502.14802) đã thay bằng explicit edge** `(passage)-[:contains]->(phrase)` — xác nhận explicit edge là hướng hiện đại.

Nguồn: [arxiv 2405.14831](https://arxiv.org/html/2405.14831v1) · [HippoRAG repo](https://github.com/osu-nlp-group/hipporag) · [HippoRAG2 2502.14802](https://arxiv.org/abs/2502.14802)

### F4 — Build backbone bằng LLM OpenIE HOẶC fixed ontology (HIGH, 3-0)

Hai cách hợp lệ, đều KHÔNG cần model mới:
- **LLM OpenIE**: extract triple/entity per passage (HippoRAG dùng GPT-3.5 v1 / Llama-3.3-70B v2). PTalk dùng **LLM router** sẵn có.
- **Fixed ontology**: TrueLearn seed concept từ Wikipedia (mỗi page = 1 KC), auto-link resource bằng entity linking — tránh expert labelling đắt mà vẫn interpretable. PTalk dùng **danh mục concept chương trình GDPT 2018** làm ontology.

> ⚠️ "no embeddings" sai — HippoRAG vẫn dùng encoder vector cho synonymy. Nghĩa là "không CHỈ embedding". PTalk đã có BGE-m3 cho vai trò này.

Nguồn: [HippoRAG repo](https://github.com/osu-nlp-group/hipporag) · [arxiv 2405.14831](https://arxiv.org/abs/2405.14831) · [TrueLearn 1911.09471](https://arxiv.org/pdf/1911.09471)

### F5 — MATH = 3-LAYER graph + prereq seed từ curriculum (HIGH, 3-0)

`(lesson/Exercise node) ↔ (KC/concept node) ↔ (prerequisite DAG trên KC)`.

- Exercise map tới KC nó luyện (**Q-matrix** convention) — lớp này tách khỏi DAG prereq (chỉ chứa edge "học X trước Y" giữa concept).
- **Prereq seed từ chuẩn chương trình**: CCSS Progressions = 18 narrative doc, mỗi cái track 1 strand qua nhiều lớp (Fractions 3-5 → Ratios & Proportional 6-7...). Chính là chuỗi **phân số → tỉ số → tỉ lệ thức** cross-grade.

> ⚠️ CCSS Progressions là narrative coherence doc, **KHÔNG phải learning trajectory đã validate**. Chúng **SEED candidate edge**, không certify thứ tự mastery. (Biến thể "standards đã encode validated builds-on link" bị REFUTE 1-2.)

→ Toán: lesson/exercise chunk (doc-level) → concept node; **DAG prereq mỏng trên concept**, seed từ strand structure GDPT 2018.

Nguồn: [arxiv 2402.01672](https://arxiv.org/pdf/2402.01672) · [CCSS Progressions](https://mathematicalmusings.org/wp-content/uploads/2023/02/Progressions.pdf) · [Springer IJAIED](https://link.springer.com/article/10.1007/s40593-020-00212-4)

### F6 — LITERATURE: tách recitation khỏi analytical; variant → 1 work node (MEDIUM, extrapolated)

Cùng pattern decouple, nhưng "concept" mỏng hơn (1 tác phẩm/chủ đề/skill-section thay vì KC toán).
- **Tách verbatim recitation** (thơ/văn đọc nguyên văn) thành node type riêng khỏi analytical chunk.
- **Nhiều depth-variant** (chi tiết vs siêu ngắn) = nhiều Document node riêng, đều `COVERS` **1 work/concept node chung** → không nhân bản concept.

> ⚠️ MEDIUM confidence: KHÔNG có nguồn literature-specific nào sống sót verify. Đây là pattern decouple **transfer** sang Văn + corroborate bằng schema PTalk sẵn có (RecitationSegment/LiteratureText đã tách khỏi KnowledgeChunk).

Nguồn: transfer từ F1 + schema hiện tại PTalk.

### F7 — Extraction chunk-size ≠ retrieval chunk-size (HIGH, 3-0)

Chunk lớn **làm hỏng** entity extraction: Microsoft HotPotQA — chunk 600-token extract **~2x** entity so với 2400-token. RAKG (2504.09823) gọi là "long-context forgetting".

→ KHÔNG cấm document-level **retrieval**. Nhưng nếu **auto-extract** concept backbone, chạy extraction trên **span nhỏ hơn** (per-section), rồi attach concept vào chunk lớn qua edge. **Lớp decouple chính là thứ cho phép retrieval-size ≠ extraction-size.**

Nguồn: [microsoft GraphRAG](https://microsoft.github.io/graphrag/index/default_dataflow/) · [RAKG 2504.09823](https://arxiv.org/abs/2504.09823)

### F8 — Mastery = vector per-concept + vị trí trong cấu trúc (HIGH, 3-0)

- **TrueLearn**: skill học sinh = θ = (θ₁...θ_N), 1 latent param/concept, update online sau mỗi event.
- **KST/ALEKS**: mastery = "vị trí trong lattice tri thức" của domain có cấu trúc cao (hình học/đại số/vật lý) — không phải điểm phẳng. ALEKS deploy ở scale với hàng triệu "knowledge state".

→ "Bài 5 build trên Bài 3 em đã học" = traverse DAG prereq từ lesson hiện tại; "position" = ranh giới giữa concept đã-mastered và chưa.

> ⚠️ Math fit sạch (KST domains = hình/đại/lý). **Văn concept structure lỏng → lattice yếu hơn nhiều.**

Nguồn: [TrueLearn 1911.09471](https://arxiv.org/pdf/1911.09471) · [Springer IJAIED](https://link.springer.com/article/10.1007/s40593-020-00212-4)

### F9 — No-quiz: infer mastery ngầm từ dialogue (HIGH, 3-0)

- Scarlatos/Baker/Lan (**LAK 2025**, 2409.16490): trace knowledge từ dialogue mở KHÔNG quiz — coi mỗi cặp (tutor-turn, student-turn) là formative assessment, LLM label correctness y∈{0,1}. Validate trên **188 dialogue Khanmigo thật**: GPT-4o đạt **75.8%** vs human **85.6%** ("close to human-level").
- Winne (2020): process trace (tagging/searching/note-taking) — không phải điểm quiz — feed learner model. Corroborate bởi BKT deploy ở ASSISTments.

> ⚠️ Kết quả KT dialogue này **CHỈ cho MATH** (tác giả: chưa chứng minh generalize). → defensible cho Toán, **speculative cho Văn**.
> ⚠️ Prereq edge **nên seed từ curriculum**, KHÔNG từ telemetry (xem refuted).

Nguồn: [LAK 2025 2409.16490](https://arxiv.org/abs/2409.16490) · [Springer IJAIED](https://link.springer.com/article/10.1007/s40593-020-00212-4)

---

## 8 claims REFUTED — KHÔNG design dựa trên những cái này

| Claim bị bác | Vote | Vì sao nguy hiểm |
|---|---|---|
| Chunk→entity edge tạo được **không cần** lexical graph | 0-3 | Phải có Document/Chunk node trước |
| GraphRAG framework extract strictly trong 1 chunk → miss cross-passage relation (failure mode trung tâm) | 0-3 | Nguồn 2605.28004 không verify được |
| LLM auto-tag mỗi dialogue turn với KC → bỏ manual tagging | 0-3 | **Đừng** giả định free auto-KC-tagging hội thoại |
| Binary "do you know this?" prompt = đủ (không cần quiz) | 0-3 | RPKT vẫn cần self-report → KHÔNG phải no-quiz |
| TrueLearn infer mastery **thuần** từ engagement ngầm | 1-2 | Signal là engagement, không phải correctness — seed cautiously |
| Prereq học được **thuần** từ telemetry adjacency matrix M | 0-3 | **Prereq phải seed từ curriculum/text, KHÔNG từ trajectory** |
| Mastery = init + weighted count success/fail thuần ngầm | 1-2 | Cần thận trọng |
| CCSS standards **đã encode** validated directed builds-on edge | 1-2 | Chỉ **SEED candidate**, không certify thứ tự |

---

## Caveats quan trọng

1. **Văn schema = MEDIUM confidence** — không có nguồn literature-specific; là pattern transfer + corroborate bằng schema PTalk sẵn có.
2. **Implicit-mastery validate CHỈ cho Toán** — generalize sang Văn chưa chứng minh. → Toán làm mastery trước, Văn để sau hoặc bỏ.
3. **KST lattice = domain cấu trúc cao** (hình/đại/lý). Văn lỏng → prereq/mastery model yếu cho Văn.
4. **Rights/copyright metadata cho recitation** — câu hỏi research nêu nhưng KHÔNG nguồn nào cover → engineering decision, không phải cited pattern.
5. **KHÔNG có engineering detail nào** của Vuihoc/VioEdu/OLM/Hocmai surface được (chỉ marketing). Squirrel AI / CK-12 / K12EduKG cũng không produce confirmed claim.
6. **Deployment evidence mạnh nhất**: TrueLearn (OER thật), ALEKS/KST (scale), Khanmigo/CoMTA (dialogue học sinh thật), ASSISTments (BKT). Yếu hơn (research demo): 2402.01672, RPKT 2508.11892.
7. **Pin version** khi implement: GraphRAG default (1200-token) + library API có thể đổi giữa version.

---

## 4 open questions → đã quyết trong design doc

1. **Văn có cần prereq/mastery không**, hay chỉ work/theme/skill-section + variant? (evidence lattice = math-only) → **Quyết: Văn KHÔNG có PREREQ DAG.**
2. **Rights schema cho recitation**? → **Quyết: giữ RecitationSegment/LiteratureText riêng + thêm rights field.**
3. **Auto-extract (LLM OpenIE) vs hand-seed (curriculum ontology)**? → **Quyết: HYBRID — strand free từ `problem_type` + hand-seed prereq DAG nhỏ, auto-extract concept mịn sau.**
4. **Store mastery có đáng không**, hay chỉ current-lesson position đủ? → **Quyết: Phase 1 chỉ current-lesson position; mastery vector = Phase 3 khi có telemetry.**

→ Chi tiết: [../design/kg-schema-v3.md](../design/kg-schema-v3.md)

---

## Nguồn primary (25 fetched, 17 confirmed claims)

**Graph RAG**: Neo4j GraphRAG docs · HippoRAG (repo + 2405.14831) · HippoRAG2 (2502.14802) · Microsoft GraphRAG · RAKG (2504.09823)
**ITS / mastery**: TrueLearn (1911.09471, AAAI'20) · Winne IJAIED (s40593-020-00212-4) · prereq discovery (2402.01672) · dialogue-KT (2409.16490, LAK'25) · ALEKS/KST · RPKT (2508.11892)
**Standards**: CCSS Progressions
**Literature/rights**: TEI cit guidelines · rightsstatements.org · (không claim nào literature-specific survive)
**VN edtech**: VioEdu/FPT (chỉ marketing, KHÔNG citable)

Liên quan: [[deep-research-per-subject-2026-05-31]] (research trước, 2026-05-31) · [data audit](../../) Toán/Văn as-is
