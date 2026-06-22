#!/usr/bin/env python3
"""ENRICH STEM THEORY — làm giàu thẻ lý thuyết Toán/KHTN cho companion.

Vì sao: scenario-knowledge backtest (2026-06-22) cho thấy companion NEO đúng bài (~100%)
nhưng knowledge_correct STEM thấp (Toán 1.27/2, KHTN 1.50/2) + hallucination cao
(Toán 25%, KHTN 18.8%) — do theory cũ MỎNG (dinh_nghia 1-3 câu + 3-4 ý + 1 ví dụ),
không phủ đủ câu hỏi chi tiết => judge thấy thiếu hoặc "ngoài theory".

Cách: re-synth theory STEM với schema DÀY hơn (giải thích sâu + điều kiện áp dụng +
2-3 ví dụ có lời giải + sai lầm thường gặp), grounded trên CHÍNH source SGK (không bịa).
MERGE đè theory chunk cũ (cùng uid) + re-embed BGE. Idempotent. Chỉ family math/science.

Usage: enrich_stem_theory.py <subject> <grade> <book> [tap|auto]
Env: EDU_NEO4J_PW, EDU_NEO4J_URI(opt), GEMMA_KEY, GEMMA_URL(opt).

So sánh trước/sau bằng scripts/scenario_backtest.py trên cùng quyển.
"""
import sys, json, re, urllib.request, unicodedata, os
os.environ['HF_HOME'] = "/home/namnx/.cache/huggingface"
from neo4j import GraphDatabase
from sentence_transformers import SentenceTransformer

SUBJECT = sys.argv[1]; GRADE = int(sys.argv[2]); BOOK = sys.argv[3]
TAP_ARG = sys.argv[4] if len(sys.argv) > 4 else "auto"
NEO = GraphDatabase.driver(os.environ.get("EDU_NEO4J_URI", "bolt://localhost:7688"),
                           auth=("neo4j", os.environ.get("EDU_NEO4J_PW", "")))
GEMMA_URL = os.environ.get("GEMMA_URL", "http://localhost:8080/v1/chat/completions")
GKEY = os.environ.get("GEMMA_KEY", "")
ACTOR = f"{SUBJECT.upper()}_ENRICH_2026_06"  # distinct actor → reversible

FAMILY = {"toan": "math", "khtn": "science", "vat_li": "science", "hoa_hoc": "science",
          "sinh_hoc": "science", "cong_nghe": "science"}
fam = FAMILY.get(SUBJECT)
if fam is None:
    print(f"[abort] {SUBJECT} không phải STEM (chỉ toan/khtn/...). Dùng build_book_generic cho môn khác.")
    sys.exit(0)

# ── ENRICHED schema: dày hơn hẳn build_book_generic (giải thích + điều kiện + nhiều ví dụ + sai lầm) ──
SCHEMA = (
 '{'
 '"dinh_nghia":"<khái niệm cốt lõi, ĐẦY ĐỦ 2-3 câu, nêu rõ bản chất>",'
 '"giai_thich":"<giải thích SÂU: vì sao/ý nghĩa/bản chất, 2-4 câu, để học sinh HIỂU chứ không học vẹt>",'
 '"kien_thuc_chinh":["<5-6 ý, MỖI ý là 1 câu đầy đủ có giải thích ngắn, không chỉ là nhãn>"],'
 '"cong_thuc":["<công thức kèm CHÚ THÍCH từng ký hiệu, hoặc [] nếu không có>"],'
 '"dieu_kien_ap_dung":"<KHI NÀO dùng/điều kiện/trường hợp đặc biệt, 1-3 câu — quan trọng cho câu hỏi vận dụng>",'
 '"vi_du":[{"de":"<đề có số/tình huống cụ thể>","giai":"<các BƯỚC giải + kết quả rõ ràng>"},{"de":"<ví dụ 2 khác dạng>","giai":"<lời giải>"}],'
 '"sai_lam_thuong_gap":"<1-2 lỗi học sinh hay mắc khi làm dạng này>",'
 '"luu_y":"<mẹo/điểm cần nhớ, 1-2 câu>",'
 '"cau_hoi_dan_dat":["<3 câu gợi mở>"],'
 '"practice":[{"cau":"Câu 1","cau_hoi":"..","goi_y":"..","dap_an":".."},{"cau":"Câu 2","cau_hoi":"..","goi_y":"..","dap_an":".."},{"cau":"Câu 3","cau_hoi":"..","goi_y":"..","dap_an":".."}]'
 '}'
)
ROLE = {"math": "giáo viên Toán", "science": "giáo viên Khoa học tự nhiên"}[fam]

def gemma(sysp, usr, mx=3600):
    body = json.dumps({"model": "gemma-4", "messages": [{"role": "system", "content": sysp},
            {"role": "user", "content": usr}], "temperature": 0.1, "max_tokens": mx}).encode()
    r = urllib.request.Request(GEMMA_URL, data=body,
            headers={"Authorization": f"Bearer {GKEY}", "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(r, timeout=180).read())["choices"][0]["message"]["content"]

def fold(s):
    s = (s or "").replace("đ", "d").replace("Đ", "D").replace("–", "-")
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()

def sanitize(t):
    t = t or ""; t = re.sub(r"Toán - Văn - Anh[^\n]*", "", t)
    t = re.sub(r"\(Giáo viên VietJack\)|Xem lời giải|Xem chi tiết|Bài giảng:.*|Video Giải[^\n]*|Giải bài nhanh với AI Hay", "", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()

# ── 1. pull existing STEM lessons (work_name, tap, source from raw SGK chunk by title) ──
with NEO.session() as s:
    lessons = s.run("""MATCH (l:Lesson {subject_code:$s,grade:$g,bo_sach:$b})-[:HAS_THEORY]->(k:KnowledgeChunk)
        WHERE ($tap='auto' OR l.tap_no=toInteger($tap) OR ($tap='none' AND l.tap_no IS NULL))
        RETURN l.lesson_id AS lid, l.work_name AS work, l.work_name_norm AS wn, l.tap_no AS tap,
               l.lesson_no AS ln, l.trang_from AS tf, l.trang_to AS tt, k.uid AS uid, k.title AS ktitle
        ORDER BY l.lesson_no""", s=SUBJECT, g=GRADE, b=BOOK, tap=TAP_ARG).data()
    # source SGK text per work (best-effort: raw chunk whose title mentions the work / Bài N)
    for c in lessons:
        src = s.run("""MATCH (k:KnowledgeChunk {subject_code:$s,grade:$g,bo_sach:$b})
            WHERE k.title =~ ('.*[Bb]ài ' + toString($ln) + '[^0-9].*') AND k.content_type IS NULL
            RETURN k.text AS text ORDER BY size(k.text) DESC LIMIT 1""",
            s=SUBJECT, g=GRADE, b=BOOK, ln=c["ln"]).single()
        c["src"] = sanitize((src["text"] if src else "") or "")
print(f"[{SUBJECT} {GRADE} {BOOK}] {len(lessons)} STEM lesson để enrich (family={fam})", flush=True)
if not lessons:
    print("NO LESSONS — abort"); sys.exit(0)

# ── 2. enriched synth ──
SYS = (f"Bạn là {ROLE} lớp {GRADE} (GDPT 2018) soạn THẺ KIẾN THỨC ĐẦY ĐỦ để chatbot ĐỒNG HÀNH cùng học sinh tự học. "
 "Thẻ phải đủ SÂU để trả lời được câu hỏi vận dụng (khái niệm, điều kiện áp dụng, ví dụ có lời giải, sai lầm hay gặp), "
 "nhưng TUYỆT ĐỐI bám nội dung SGK kèm theo + kiến thức chuẩn của bài, KHÔNG bịa số liệu/sự kiện. "
 "Chỉ trả JSON đúng định dạng, tiếng Việt:\n" + SCHEMA)
ok = 0
for c in lessons:
    base = c["src"][:6000] if c.get("src") else ""
    usr = f"TÊN BÀI: {c['work']}\nMÔN: {SUBJECT} lớp {GRADE} {BOOK}\n\nNỘI DUNG SGK (trích, để bám sát):\n{base or '(không có trích — dựa kiến thức chuẩn của bài này trong chương trình)'}"
    try:
        raw = gemma(SYS, usr).replace("```json", "").replace("```", "").strip()
        m = re.search(r"\{.*\}", raw, re.S); c.update(json.loads(m.group(0) if m else raw)); c["_ok"] = True
        ok += 1
        print(f"  OK B{c['ln']} {c['work'][:42]:44} tap={c['tap']}", flush=True)
    except Exception as e:
        c["_ok"] = False; print(f"  ERR B{c['ln']} {c['work'][:42]} -> {e}", flush=True)

# ── 3. enriched card_text ──
def card_text(c):
    L = [f"Bài: {c['work']} ({SUBJECT} lớp {GRADE} {BOOK})"]
    if c.get("dinh_nghia"): L.append(f"Khái niệm: {c['dinh_nghia']}")
    if c.get("giai_thich"): L.append(f"Giải thích: {c['giai_thich']}")
    if c.get("kien_thuc_chinh"): L.append("Kiến thức chính:\n- " + "\n- ".join(c["kien_thuc_chinh"]))
    if c.get("cong_thuc"): L.append("Công thức / Quy tắc:\n- " + "\n- ".join(c["cong_thuc"]))
    if c.get("dieu_kien_ap_dung"): L.append(f"Điều kiện áp dụng: {c['dieu_kien_ap_dung']}")
    if c.get("vi_du"): L.append("Ví dụ:\n" + "\n".join(f"- {e.get('de','')} → {e.get('giai','')}" for e in c["vi_du"]))
    if c.get("sai_lam_thuong_gap"): L.append(f"Sai lầm thường gặp: {c['sai_lam_thuong_gap']}")
    if c.get("luu_y"): L.append(f"Lưu ý: {c['luu_y']}")
    return "\n".join(L)

print("[ingest] load BGE...", flush=True); bge = SentenceTransformer("BAAI/bge-m3"); print("[ingest] BGE ok", flush=True)
st = {"upd": 0, "skip": 0}
with NEO.session() as s:
    for c in lessons:
        if not c.get("_ok"): st["skip"] += 1; continue
        text = card_text(c)
        if len(text) < 80: st["skip"] += 1; continue   # enriched should be substantial
        emb = bge.encode([text], normalize_embeddings=True)[0].tolist()
        gq = json.dumps(c.get("cau_hoi_dan_dat", []), ensure_ascii=False)
        pj = json.dumps(c.get("practice", []), ensure_ascii=False)
        # update the EXISTING theory chunk (same uid) — keep edges; mark enriched actor
        s.run("""MATCH (k:KnowledgeChunk {uid:$uid})
            SET k.text=$text, k.embedding=$emb, k.embedding_model='bge-m3',
                k.source='gemma_synth_enriched', k.ingest_actor=$actor, k.guiding_questions=$gq,
                k.enriched_2026_06=true""",
            uid=c["uid"], text=text, emb=emb, actor=ACTOR, gq=gq)
        # refresh practice on the lesson too (richer practice)
        s.run("MATCH (l:Lesson {lesson_id:$lid}) SET l.practice_json=$pj, l.ingest_actor=$actor",
              lid=c["lid"], pj=pj, actor=ACTOR)
        st["upd"] += 1
NEO.close()
print(f"\nDONE ENRICH {SUBJECT} {GRADE} {BOOK}: updated={st['upd']} skip={st['skip']} (synth_ok={ok}/{len(lessons)})", flush=True)
