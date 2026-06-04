import unicodedata
from neo4j import GraphDatabase
drv=GraphDatabase.driver("bolt://localhost:7688",auth=("neo4j","CHANGEME_NEO4J_PASS"))
def fold(s):
    s=(s or "").replace("đ","d").replace("Đ","D"); s=unicodedata.normalize("NFD",s)
    return "".join(c for c in s if unicodedata.category(c)!="Mn").lower()
with drv.session() as s:
    rows=list(s.run("MATCH (c:Concept) WHERE c.name IS NOT NULL RETURN c.concept_id AS id, c.name AS name"))
    fixed=0
    for r in rows:
        nf=fold(r["name"])
        s.run("MATCH (c:Concept {concept_id:$id}) SET c.name_norm=$nf", id=r["id"], nf=nf)
        fixed+=1
    print(f"re-normalized name_norm (đ→d) on {fixed} concepts")
    # sample to confirm
    for r in s.run("MATCH (c:Concept) WHERE c.name CONTAINS 'Định' RETURN c.name AS n, c.name_norm AS nf LIMIT 3"):
        print(f"  {r['n']!r} → {r['nf']!r}")
drv.close()
