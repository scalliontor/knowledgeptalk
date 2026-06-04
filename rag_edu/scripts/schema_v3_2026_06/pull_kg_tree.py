import json
from neo4j import GraphDatabase
drv=GraphDatabase.driver("bolt://localhost:7688",auth=("neo4j","CHANGEME_NEO4J_PASS"))
SUBJ={"toan":"Toán","ngu_van":"Ngữ văn","tieng_viet":"Tiếng Việt","khtn":"KHTN",
      "lich_su":"Lịch sử","dia_li":"Địa lý","gdcd":"GDCD","vat_li":"Vật lý","hoa_hoc":"Hóa học","sinh_hoc":"Sinh học"}
with drv.session() as s:
    rows=list(s.run("""
      MATCH (k:KnowledgeChunk) WHERE k.production_ready=true AND k.subject_code IN $subs
      RETURN k.subject_code AS subj, toInteger(k.grade) AS g, coalesce(k.bo_sach,'NONE') AS bo,
             count(*) AS chunks,
             count(DISTINCT k.lesson_no) AS lessons,
             count(DISTINCT k.trang_no) AS pages
    """, subs=list(SUBJ.keys())))
    # concepts per (subj,g,bo)
    crows=list(s.run("""
      MATCH (k:KnowledgeChunk)-[:COVERS]->(c:Concept) WHERE k.production_ready=true AND k.subject_code IN $subs
      RETURN k.subject_code AS subj, toInteger(k.grade) AS g, coalesce(k.bo_sach,'NONE') AS bo, count(DISTINCT c) AS concepts
    """, subs=list(SUBJ.keys())))
    works=list(s.run("MATCH (w:LiteraryWork) RETURN count(w) AS n")).pop() if False else None
    totals=s.run("""MATCH (k:KnowledgeChunk) WHERE k.production_ready=true RETURN count(*) AS chunks""").single()
    nconcept=s.run("MATCH (c:Concept) RETURN count(c) AS n").single()["n"]
    ncovers=s.run("MATCH ()-[r:COVERS]->() RETURN count(r) AS n").single()["n"]
    nworks=s.run("MATCH (w:LiteraryWork) RETURN count(w) AS n").single()["n"]
cmap={(r["subj"],r["g"],r["bo"]):r["concepts"] for r in crows}
data=[]
for r in rows:
    d=dict(r); d["concepts"]=cmap.get((r["subj"],r["g"],r["bo"]),0); d["subj_vi"]=SUBJ.get(r["subj"],r["subj"]); data.append(d)
out={"cells":data,"totals":{"prod_chunks":totals["chunks"],"concepts":nconcept,"covers":ncovers,"works":nworks}}
print(json.dumps(out,ensure_ascii=False))
drv.close()
