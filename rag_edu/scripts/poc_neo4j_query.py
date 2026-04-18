import json
from neo4j import GraphDatabase

URI = "bolt://localhost:7687"
AUTH = ("neo4j", "legal_graph_2026")

def test_query():
    with GraphDatabase.driver(URI, auth=AUTH) as driver:
        with driver.session() as session:
            # Câu hỏi: Trích xuất Dữ liệu Lời Giải cho Câu 1 của "Nhát đinh của bác thợ"
            print("=== HỆ THỐNG TRUY VẤN GRAPH-RAG (PoC) ===\n")
            
            # Query 1: Lấy các câu hỏi học thuật thuộc về Ngữ liệu
            print(">> Truy vấn 1: Tìm câu hỏi số 1 và lời giải tương ứng...")
            query = """
            MATCH (s:Solution)-[:SOLVES]->(q:Question)
            WHERE q.raw_text CONTAINS 'Câu 1'
            RETURN q.contextualized_text AS Question, s.raw_text AS Solution
            """
            
            results = session.run(query)
            for record in results:
                print(f"[QUESTION]: {record['Question']}")
                print(f"[SOLUTION]: {record['Solution']}\n")
                
            # Query 2: In toàn bộ Flow của Đồ Thị
            print(">> Truy vấn 2: Path Traversal (Solution -> Question)")
            query_path = """
            MATCH path = (s:Solution)-[r]->(q:Question)
            RETURN s.node_id AS S_ID, type(r) AS Edge, q.node_id AS Q_ID
            LIMIT 5
            """
            paths = session.run(query_path)
            for p in paths:
                print(f"({p['S_ID']}) --[{p['Edge']}]--> ({p['Q_ID']})")

if __name__ == "__main__":
    test_query()
