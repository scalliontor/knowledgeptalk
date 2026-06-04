#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Verify kiến trúc RAG Toán — Gemma4 sinh test case học sinh hỏi bài,
4 loại: theo trang / theo bài / hỏi kiến thức / cách giải.
Chạy trên server (Gemma4 :8080 + canary :8889 + Neo4j :7688 đều localhost).
"""
import json, re, sys, unicodedata
import requests
from neo4j import GraphDatabase

NEO4J_URI = "bolt://localhost:7688"
NEO4J_AUTH = ("neo4j", "CHANGEME_NEO4J_PASS")
GEMMA_URL = "http://localhost:8080/v1/chat/completions"
GEMMA_KEY = "CHANGEME_GEMMA_KEY"
CANARY = "http://localhost:8889/retrieve"

def fold(s):
    s = unicodedata.normalize('NFD', s or '')
    return ''.join(c for c in s if unicodedata.category(c) != 'Mn').lower()

# ── 1. Pull real anchors from Neo4j ───────────────────────────
def pull_anchors():
    drv = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    anchors = []
    with drv.session() as s:
        # Lesson anchors (clean Bài N: concept) — for theo-bài / kiến thức / cách giải
        q_lesson = """
        MATCH (k:KnowledgeChunk)
        WHERE k.subject_code='toan' AND k.production_ready=true
          AND k.content_class='vietjack_lesson' AND k.lesson_no IS NOT NULL
          AND k.title =~ '.*Bài \\\\d+:.*'
        WITH k, split(k.title, ': ')[-1] AS concept
        WHERE size(concept) > 3 AND size(concept) < 50
        RETURN k.grade AS grade, k.bo_sach AS bo_sach, k.lesson_no AS lesson_no,
               concept AS concept, k.title AS title, k.uid AS uid
        ORDER BY rand() LIMIT 8
        """
        for r in s.run(q_lesson):
            anchors.append({"kind":"lesson", **dict(r)})
        # Exercise/page anchors (có trang_no) — for theo-trang
        q_page = """
        MATCH (k:KnowledgeChunk)
        WHERE k.subject_code='toan' AND k.production_ready=true
          AND k.trang_no IS NOT NULL
        RETURN k.grade AS grade, k.bo_sach AS bo_sach, k.trang_no AS trang_no,
               k.title AS title, k.uid AS uid
        ORDER BY rand() LIMIT 5
        """
        for r in s.run(q_page):
            anchors.append({"kind":"page", **dict(r)})
    drv.close()
    return anchors

# ── 2. Gemma4 sinh query tự nhiên giọng học sinh ──────────────
def gemma(prompt, sys_msg="Bạn mô phỏng học sinh tiểu học/THCS Việt Nam nói chuyện với gia sư AI."):
    body = {
        "model": "gemma-4",
        "messages": [{"role":"system","content":sys_msg},
                     {"role":"user","content":prompt}],
        "max_tokens": 120, "temperature": 0.8,
    }
    r = requests.post(GEMMA_URL, headers={"Authorization":f"Bearer {GEMMA_KEY}"},
                      json=body, timeout=60)
    return r.json()["choices"][0]["message"]["content"].strip()

def make_query(anchor, qtype):
    g, bo = anchor["grade"], anchor["bo_sach"]
    if qtype == "theo_trang":
        p = (f"Em đang học Toán lớp {g}, sách {bo}, đang mở trang {anchor['trang_no']}. "
             f"Hãy viết MỘT câu nói tự nhiên (giọng nói, ngắn) em hỏi gia sư để được giải bài ở trang đó. "
             f"Chỉ trả về câu hỏi, không giải thích.")
    elif qtype == "theo_bai":
        p = (f"Em học Toán lớp {g} sách {bo}, đang làm Bài {anchor['lesson_no']} '{anchor['concept']}'. "
             f"Viết MỘT câu nói tự nhiên em nhờ gia sư giảng bài này. Chỉ câu hỏi, ngắn gọn.")
    elif qtype == "kien_thuc":
        p = (f"Em học Toán lớp {g}. Viết MỘT câu hỏi tự nhiên em hỏi gia sư về khái niệm '{anchor['concept']}' là gì. "
             f"Chỉ câu hỏi, ngắn gọn, giọng trẻ con.")
    elif qtype == "cach_giai":
        p = (f"Em học Toán lớp {g}. Viết MỘT câu hỏi tự nhiên em hỏi gia sư CÁCH GIẢI / cách làm dạng bài '{anchor['concept']}'. "
             f"Chỉ câu hỏi, ngắn gọn.")
    q = gemma(p).strip().strip('"').split("\n")[0]
    return q

# ── 3. Run canary /retrieve ───────────────────────────────────
def retrieve(query, grade, bo_sach):
    body = {"query": query, "user_profile": {"lop": grade, "bo_sach": bo_sach}}
    try:
        r = requests.post(CANARY, json=body, timeout=60)
        return r.json()
    except Exception as e:
        return {"error": str(e)}

# ── 4. Score ──────────────────────────────────────────────────
def score(anchor, qtype, resp):
    ctx = fold(resp.get("context",""))
    intent = resp.get("intent",{})
    sources = resp.get("sources",[])
    hit = {"tier": intent.get("tier") or (sources[0] if sources else "none"),
           "sources": sources, "ctx_len": len(resp.get("context",""))}
    # expected signal in context
    if qtype in ("theo_bai","kien_thuc","cach_giai"):
        concept_f = fold(anchor.get("concept",""))
        hit["concept_match"] = concept_f in ctx if concept_f else None
    if qtype in ("theo_trang",):
        hit["trang_match"] = (f"trang {anchor['trang_no']}" in ctx) or (str(anchor['trang_no']) in ctx)
    # grade/book leak check
    g = anchor["grade"]
    other_grades = [str(x) for x in range(1,13) if x != g]
    hit["grade_ok"] = (f"lop {g}" in ctx or f"lớp {g}" in fold(resp.get('context','')) or ctx=="")
    return hit

def main():
    print("=== Pull anchors ===")
    anchors = pull_anchors()
    print(f"Got {len(anchors)} anchors")
    cases = []
    for a in anchors:
        if a["kind"] == "page":
            types = ["theo_trang"]
        else:
            types = ["theo_bai","kien_thuc","cach_giai"]
        for t in types:
            try:
                q = make_query(a, t)
            except Exception as e:
                q = f"[gemma_err:{e}]"
            cases.append({"anchor":a, "qtype":t, "query":q})
    print(f"Generated {len(cases)} test cases\n")
    results = []
    for c in cases:
        resp = retrieve(c["query"], c["anchor"]["grade"], c["anchor"]["bo_sach"])
        sc = score(c["anchor"], c["qtype"], resp) if "error" not in resp else {"error":resp["error"]}
        results.append({**c, "score":sc})
        a = c["anchor"]
        ref = f"B{a.get('lesson_no','-')}/{a.get('concept', 'trang'+str(a.get('trang_no','')))}"
        print(f"[{c['qtype']:11}] G{a['grade']} {a['bo_sach']:4} {ref[:32]:32} | tier={sc.get('tier','?'):20} concept={sc.get('concept_match')} trang={sc.get('trang_match')}")
        print(f"    Q: {c['query'][:100]}")
    # summary
    print("\n=== SUMMARY by type ===")
    from collections import defaultdict
    agg = defaultdict(lambda: {"n":0,"tier_a":0,"concept_hit":0,"trang_hit":0,"nonempty":0})
    for r in results:
        t = r["qtype"]; sc = r["score"]
        agg[t]["n"] += 1
        if "tier_a" in str(sc.get("tier","")) or sc.get("tier")=="A_structured": agg[t]["tier_a"] += 1
        if sc.get("concept_match"): agg[t]["concept_hit"] += 1
        if sc.get("trang_match"): agg[t]["trang_hit"] += 1
        if sc.get("ctx_len",0) > 0: agg[t]["nonempty"] += 1
    for t,v in agg.items():
        print(f"{t:12}: n={v['n']} nonempty={v['nonempty']} tierA={v['tier_a']} concept_hit={v['concept_hit']} trang_hit={v['trang_hit']}")
    # dump full
    with open("/tmp/verify_arch_results.json","w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("\nFull → /tmp/verify_arch_results.json")

if __name__ == "__main__":
    main()
