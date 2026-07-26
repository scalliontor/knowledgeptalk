# -*- coding: utf-8 -*-
"""Bổ sung alias cho thẻ GOLD:
 (a) alias NGẮN dùng chung -> kích hoạt sibling-guard ('điện biên phủ')
 (b) alias MÔ TẢ cho câu ĐỐ NGƯỢC (mô tả -> tên): 'tổng bí thư đầu tiên', 'trạng nguyên trẻ nhất'
Data-only, reversible theo ingest_batch."""
import re, unicodedata
import os
from neo4j import GraphDatabase

BATCH = "histalias_v2_2026_07_26"
def fold(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").replace("đ", "d")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s)).strip()

# name_norm thẻ  ->  alias thêm
ADD = {
    "chien dich dien bien phu": ["điện biên phủ", "trận điện biên phủ 1954"],
    "chien dich dien bien phu tren khong": ["điện biên phủ trên không", "trận điện biên phủ trên không"],
    "hiep dinh gio ne vo ve dong duong": ["hiệp định giơ ne vơ", "hiệp định giơnevơ", "hiệp định geneve", "giơ ne vơ"],
    "tran phu": ["tổng bí thư đầu tiên", "tổng bí thư đầu tiên của đảng", "tbt đầu tiên"],
    "nguyen hien": ["trạng nguyên trẻ tuổi nhất", "trạng nguyên trẻ nhất", "trạng nguyên 13 tuổi", "ông trạng thả diều"],
    "vua duc duc": ["vua trị vì ngắn nhất", "vị vua trị vì ngắn nhất", "vua ở ngôi ngắn nhất"],
    "nguyen trung truc": ["hết cỏ nước nam", "bao giờ hết cỏ nước nam"],
    "hong quan lien xo": ["hồng quân", "quân đội đỏ"],
    "hoi viet nam cach mang thanh nien": ["việt nam cách mạng thanh niên", "hội vncmtn"],
    "ke hoach na va": ["kế hoạch nava", "kế hoạch na va"],
    "hoi nghi vec xai": ["hội nghị véc xai", "hội nghị vecsai", "hội nghị versailles", "hội nghị hòa bình"],
    "dai hoi dai bieu toan quoc lan thu ba cua dang": ["đại hội iii", "đại hội lần thứ ba của đảng", "đại hội đảng lần thứ 3"],
    "dai hoi dai bieu lan thu hai cua dang": ["đại hội ii", "đại hội lần thứ hai của đảng", "đại hội đảng lần thứ 2"],
    "ke hoach xta lay tay lo": ["kế hoạch staley taylor", "xta lây tay lo"],
    "ke hoach do lat do tat xi nhi": ["kế hoạch đờ lát", "đờ lát đơ tát xi nhi"],
    "cuoc dai khung hoang kinh te the gioi": ["đại khủng hoảng kinh tế", "khủng hoảng kinh tế thế giới", "đại suy thoái"],
    "nhat dao chinh phap": ["nhật đảo chính", "đảo chính pháp"],
    "cuoc tien cong chien luoc dong xuan 1953 1954": ["đông xuân 1953 1954", "tiến công chiến lược đông xuân"],
    "chien dich viet bac thu dong 1947": ["chiến dịch việt bắc", "việt bắc thu đông"],
    "cong xa pa ri": ["công xã pari", "công xã paris"],
    "khoi nghia xi pay": ["khởi nghĩa xipay", "khởi nghĩa sepoy", "xi pay"],
    "phong trao can vuong": ["cần vương", "phong trào cần vương"],
    "nam bo khang chien": ["ủy ban kháng chiến nam bộ", "ngày nam bộ kháng chiến"],
    "mat tran dan toc giai phong mien nam viet nam": ["mặt trận dân tộc giải phóng miền nam", "mặt trận giải phóng miền nam"],
    "tam uoc viet phap": ["tạm ước", "tạm ước 14 9 1946", "tạm ước 14 tháng 9"],
    "phong trao xo viet nghe tinh": ["xô viết nghệ tĩnh", "xô viết nghệ an hà tĩnh"],
}

drv = GraphDatabase.driver(os.getenv("EDU_NEO4J_URI", "bolt://localhost:7688"),
                          auth=(os.getenv("EDU_NEO4J_USER", "neo4j"), os.environ["EDU_NEO4J_PASS"]))
added = miss = 0
with drv.session() as s:
    for nn, als in ADD.items():
        hit = s.run("MATCH (h:HistEvent {name_norm:$nn, verified:true}) RETURN elementId(h) AS e", nn=nn).data()
        if not hit:
            print(f"  [!] không thấy thẻ gold: {nn}"); miss += 1; continue
        for e in [x["e"] for x in hit]:
            for a in als:
                af = fold(a)
                if not af: continue
                s.run("""MERGE (al:HistAlias {value_norm:$a})
                         ON CREATE SET al.ingest_batch=$b
                         WITH al MATCH (h) WHERE elementId(h)=$e
                         MERGE (al)-[:ALIAS_OF]->(h)""", a=af, e=e, b=BATCH)
                added += 1
print(f"alias thêm: {added} | thẻ không tìm thấy: {miss}")

# liệt kê tên thẻ gold để đối chiếu name_norm
with drv.session() as s:
    print("\n=== THẺ GOLD (name_norm) ===")
    for x in s.run("MATCH (h:HistEvent {verified:true}) RETURN h.name_norm AS nn, h.canonical_name AS n ORDER BY nn"):
        print(f"  {x['nn']}")
