import json, random
from neo4j import GraphDatabase
NEO = GraphDatabase.driver(
    __import__("os").environ.get("EDU_NEO4J_URI", "bolt://localhost:7688"),
    auth=("neo4j", __import__("os").environ.get("EDU_NEO4J_PW", "")),
)
SUBJ = ["toan", "khtn", "lich_su", "dia_li", "gdcd", "ngu_van"]
cases = []
with NEO.session() as s:
    for subj in SUBJ:
        rows = s.run("""MATCH (l:Lesson {subject_code:$s})
            WHERE l.work_name IS NOT NULL AND size(l.work_name)>=6
            WITH l, [(l)-[:HAS_RECITE]->(x)|1] AS rec ORDER BY rand() LIMIT 6
            RETURN l.work_name AS w, l.grade AS g, l.bo_sach AS b, coalesce(l.tap_no,0) AS t,
                   l.trang_from AS tf, l.trang_to AS tt, l.practice_json AS pj, size(rec) AS recite""",
            s=subj).data()
        for r in rows:
            base = {"lop": r["g"], "bo_sach": r["b"], "subject": subj}
            if r["t"]: base["tap"] = r["t"]
            cases.append({"query": "giảng bài này cho mình với", "user_profile": {**base, "current_lesson": r["w"]}})
            cases.append({"query": "giảng bài " + r["w"] + " đi", "user_profile": dict(base)})
            if r["tf"]:
                p = (r["tf"] + (r["tt"] or r["tf"])) // 2
                cases.append({"query": "bài ở trang này nói gì", "user_profile": {**base, "trang": p}})
            if r["pj"]:
                cases.append({"query": "cho mình mấy câu luyện tập bài này", "user_profile": {**base, "current_lesson": r["w"]}})
            if r["recite"]:
                cases.append({"query": "đọc thuộc bài này cho nghe", "user_profile": {**base, "current_lesson": r["w"]}})
NEO.close()
cases += [
    {"query": "hôm nay trời đẹp nhỉ", "user_profile": {"lop": 8, "bo_sach": "CTST", "subject": "toan", "tap": 1}},
    {"query": "kể chuyện cười đi", "user_profile": {}},
    {"query": "giảng bài trang 999 cho tớ", "user_profile": {"lop": 6, "bo_sach": "CTST", "subject": "toan"}},
    {"query": "giảng bài Nhớ rừng cho em", "user_profile": {"lop": 6, "bo_sach": "CTST", "subject": "ngu_van"}},
    {"query": "tập hợp số tự nhiên là gì", "user_profile": {"lop": 6, "bo_sach": "CTST", "subject": "toan"}},
    {"query": "bài 1 trang 7 nói gì", "user_profile": {"lop": 6, "bo_sach": "CTST", "subject": "toan", "tap": 1}},
]
open("/tmp/cases.jsonl", "w", encoding="utf-8").write("\n".join(json.dumps(c, ensure_ascii=False) for c in cases))
print("wrote", len(cases), "cases")
