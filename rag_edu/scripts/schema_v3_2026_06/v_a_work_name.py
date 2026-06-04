#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V-A: extract work_name from Văn soan_bai titles, GATED by section_type + activity blocklist."""
import re, unicodedata
from collections import Counter
from neo4j import GraphDatabase

drv = GraphDatabase.driver("bolt://localhost:7688", auth=("neo4j","CHANGEME_NEO4J_PASS"))
ACTOR = "V_A_2026_06_03"

def fold(s):
    s = (s or '').replace('đ','d').replace('Đ','D')
    s = unicodedata.normalize('NFD', s)
    return ''.join(c for c in s if unicodedata.category(c) != 'Mn').lower()

SKILL_PAT = re.compile(
    r'(thuc hanh tieng viet|^viet |bai van|^noi va nghe|^noi nghe|on tap|cung co|mo rong|'
    r'tri thuc ngu van|thao luan|trinh bay|gioi thieu|tom tat|^phan tich|nghi luan|'
    r'thuyet trinh|on tap hoc ki|kiem tra|^danh gia|^doc$|^viet$|'
    r'phieu hoc tap|tu danh gia|he thong hoa|ve dich|ngay hoi|doc mo rong|thuc hanh doc|'
    r'huong dan tu hoc|tra bai|de tham khao|de thi|de kiem tra|^cau hoi|^bai tap|'
    r'tong ket|^luyen tap|^bai \d+$|^chu de|du an|hoat dong|cung suy ngam|tu hoc|'
    r'^ke lai|^ke ve|trao doi|^viet bai|^viet doan|tap lam|^trinh|^thao|^noi |'
    r'tham khao|^doc hieu|^doc ket noi|^doc mo|cung co mo rong|on tap va)')

def extract_work(title):
    m = re.search(r'So[aạ]n\s+b[àa]i\s+(.+?)\s+SGK', title)
    if not m: return None
    slot = m.group(1).strip()
    return slot if 2 < len(slot) < 80 else None

with drv.session() as s:
    rows = list(s.run("""
        MATCH (k:KnowledgeChunk)
        WHERE k.subject_code='ngu_van' AND k.production_ready=true AND k.section_type='soan_bai'
        RETURN k.uid AS uid, k.title AS title, k.grade AS grade, k.bo_sach AS bo
    """))
print(f"soan_bai chunks: {len(rows)}")

work_set = Counter(); updates = []; skipped = 0
for r in rows:
    slot = extract_work(r["title"])
    if not slot:
        skipped += 1; continue
    if SKILL_PAT.search(fold(slot)):
        skipped += 1; continue
    updates.append((r["uid"], slot)); work_set[slot] += 1

print(f"work_name extracted: {len(updates)} | skipped: {skipped} | distinct works: {len(work_set)}")
print("Top 20 works:")
for w,c in work_set.most_common(20):
    print(f"  {c:3}  {w}")

with drv.session() as s:
    for uid, wn in updates:
        s.run("MATCH (k:KnowledgeChunk {uid:$uid}) SET k.work_name=$wn, k.work_actor=$a", uid=uid, wn=wn, a=ACTOR)
print(f"\nwrote work_name to {len(updates)} chunks")
with drv.session() as s:
    v = s.run("""MATCH (k:KnowledgeChunk {subject_code:'ngu_van', production_ready:true, section_type:'soan_bai'})
        RETURN count(*) AS soanbai, sum(CASE WHEN k.work_name IS NOT NULL THEN 1 ELSE 0 END) AS with_work""").single()
    print(f"VERIFY: soan_bai={v['soanbai']} with_work_name={v['with_work']}")
drv.close()
