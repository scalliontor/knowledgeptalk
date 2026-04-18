import json
import os
from neo4j import GraphDatabase

URI = "bolt://localhost:7687"
AUTH = ("neo4j", "legal_graph_2026")

def import_nodes():
    import glob
    data_dir = "/home/namnx/knowledgeforptalk/rag_edu/data/mass_corpus"
    files = glob.glob(os.path.join(data_dir, "clean_grade_*.json"))
    
    total_imported = 0
    with GraphDatabase.driver(URI, auth=AUTH) as driver:
        with driver.session() as session:
            for f_path in files:
                with open(f_path, "r", encoding="utf-8") as f:
                    nodes = json.load(f)
                
                print(f"[{os.path.basename(f_path)}] Appending {len(nodes)} Neo4j nodes...")
                if len(nodes) == 0: continue
                # We DO NOT delete data here!!! Just append!
                
                for node in nodes:
                    label = node.get("node_label", "Passage_Span")
                    node_id = node.get("node_id", "")
                    raw_text = node.get("raw_text", "").replace("'", r"\'").replace('"', r'\"')
                    ctx_text = node.get("contextualized_text", "").replace("'", r"\'").replace('"', r'\"')
                    
                    # Metadata (flattened in new spider)
                    page = node.get("dom_order", 0)
                    title = node.get("title", "")
                    url = node.get("url", "")
                    
                    # Use MERGE to insert
                    query = f"""
                    MERGE (n:{label} {{node_id: "{node_id}"}})
                    ON CREATE SET 
                        n.raw_text = "{raw_text}",
                        n.contextualized_text = "{ctx_text}",
                        n.dom_order = {page},
                        n.title = "{title}",
                        n.url = "{url}",
                        n.source = "loigiaihay"
                    ON MATCH SET
                        n.source = "loigiaihay"
                    """
                    try:
                        session.run(query)
                        total_imported += 1
                    except Exception as e:
                        pass
                        
    print(f"Successfully appended {total_imported} Passage_Span nodes across all grades!")

if __name__ == "__main__":
    import_nodes()
