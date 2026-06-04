#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T-B2: extract fine concept from Toán lesson titles 'Bài N: <name>',
dedup by normalized name, create :Concept + COVERS edges. Additive, actor-tagged."""
import re, unicodedata
from collections import defaultdict
from neo4j import GraphDatabase

drv = GraphDatabase.driver("bolt://localhost:7688", auth=("neo4j","CHANGEME_NEO4J_PASS"))
ACTOR = "T_B2_2026_06_03"

def fold(s):
    s = unicodedata.normalize('NFD', s or '')
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return re.sub(r'\s+',' ', s).strip().lower()

def slugify(s):
    f = fold(s)
    return re.sub(r'[^a-z0-9]+','_', f).strip('_')[:60]

BOOK_SUFFIX = re.compile(r'\s*[\(\|].*$')  # strip " (Kết nối...)" / " | ..."

def extract_concept(title):
    m = re.search(r'B[àa]i\s+\d+\s*:\s*(.+)', title)
    if not m: return None
    c = m.group(1).strip()
    c = BOOK_SUFFIX.sub('', c).strip()
    # strip trailing " - Cánh diều" etc (book name after dash, at very end)
    c = re.sub(r'\s*[-–]\s*(Kết nối tri thức|Chân trời sáng tạo|Cánh [Dd]iều)\s*$','', c).strip()
    return c if 3 < len(c) < 80 else None

with drv.session() as s:
    rows = list(s.run("""
        MATCH (k:KnowledgeChunk)
        WHERE k.subject_code='toan' AND k.production_ready=true
          AND k.content_class='vietjack_lesson' AND k.title =~ '.*B[àa]i \\\\d+:.*'
        RETURN k.uid AS uid, k.title AS title, k.grade AS grade,
               k.bo_sach AS bo, k.problem_type AS pt
    """))
print(f"lesson-page chunks: {len(rows)}")

# Build concept registry: name_norm -> {name, min_grade, strands, uids}
reg = {}
chunk_concept = {}  # uid -> name_norm
for r in rows:
    c = extract_concept(r["title"])
    if not c:
        continue
    nf = fold(c)
    chunk_concept[r["uid"]] = nf
    e = reg.setdefault(nf, {"name": c, "min_grade": r["grade"], "strands": set(), "n":0})
    e["n"] += 1
    if r["grade"] and (e["min_grade"] is None or r["grade"] < e["min_grade"]):
        e["min_grade"] = r["grade"]
    if r["pt"] and r["pt"] not in ("general","practice_general"):
        e["strands"].add(r["pt"])

print(f"distinct fine concepts: {len(reg)}")
print(f"chunks with extractable concept: {len(chunk_concept)}")

# Create concept nodes
with drv.session() as s:
    created = 0
    for nf, e in reg.items():
        strand = sorted(e["strands"])[0] if e["strands"] else "unclassified"
        cid = f"toan.{slugify(e['name'])}"
        s.run("""
            MERGE (c:Concept {concept_id:$cid})
            SET c.name=$name, c.name_norm=$nf, c.subject='toan',
                c.strand=$strand, c.grade_introduced=$mg,
                c.level='fine', c.source='lesson_title', c.created_actor=$actor
        """, cid=cid, name=e["name"], nf=nf, strand=strand, mg=e["min_grade"], actor=ACTOR)
        created += 1
    print(f"fine concepts created/merged: {created}")

    # COVERS edges (chunk -> fine concept), set concept_id_fine on chunk
    edges = 0
    for uid, nf in chunk_concept.items():
        cid = f"toan.{slugify(reg[nf]['name'])}"
        s.run("""
            MATCH (k:KnowledgeChunk {uid:$uid}), (c:Concept {concept_id:$cid})
            MERGE (k)-[:COVERS]->(c)
            SET k.concept_id_fine=$cid
        """, uid=uid, cid=cid)
        edges += 1
    print(f"COVERS edges (fine): {edges}")

# verify
with drv.session() as s:
    v = s.run("""
        MATCH (k:KnowledgeChunk {subject_code:'toan', production_ready:true, content_class:'vietjack_lesson'})
        RETURN count(*) AS lessons, sum(CASE WHEN k.concept_id_fine IS NOT NULL THEN 1 ELSE 0 END) AS with_fine
    """).single()
    print(f"VERIFY: lessons={v['lessons']} with_fine_concept={v['with_fine']}")
    # sample concepts
    print("Sample fine concepts:")
    for r in s.run("MATCH (c:Concept {level:'fine'}) RETURN c.name AS n, c.grade_introduced AS g, c.strand AS st ORDER BY rand() LIMIT 10"):
        print(f"  G{r['g']} [{r['st']}] {r['n']}")
drv.close()
