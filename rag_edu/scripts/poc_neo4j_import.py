import json
import os
from neo4j import GraphDatabase

URI = "bolt://localhost:7687"
AUTH = ("neo4j", "legal_graph_2026")

def import_nodes():
    data_path = "/mnt/DA0054DE0054C365/STEAM_LAB/cloud_ptalk/Knowledgeforptalk/rag_edu/graph_nodes_sample.json"
    
    if not os.path.exists(data_path):
        data_path = "graph_nodes_sample.json"
        
    with open(data_path, "r", encoding="utf-8") as f:
        nodes = json.load(f)

    with GraphDatabase.driver(URI, auth=AUTH) as driver:
        with driver.session() as session:
            # Clear old PoC data to avoid duplicates
            session.run("MATCH (n:Question) DETACH DELETE n")
            session.run("MATCH (n:Solution) DETACH DELETE n")
            session.run("MATCH (n:Passage_Span) DETACH DELETE n")
            print("Cleared old PoC data from Neo4j.")

            print(f"Importing {len(nodes)} nodes to Neo4j...")
            for node in nodes:
                label = node["node_label"]
                node_id = node["node_id"]
                raw_text = node["raw_text"].replace("'", r"\'").replace('"', r'\"')
                ctx_text = node.get("contextualized_text", "").replace("'", r"\'").replace('"', r'\"')
                
                # Metadata
                page = node.get("grounding", {}).get("dom_order", 0)
                
                # CREATE NODE
                query = f"""
                CREATE (n:{label} {{
                    node_id: "{node_id}",
                    raw_text: "{raw_text}",
                    contextualized_text: "{ctx_text}",
                    dom_order: {page}
                }})
                """
                session.run(query)

            # Pass 2: Create Edges
            edge_count = 0
            for node in nodes:
                node_id = node["node_id"]
                edges = node.get("edges", [])
                for edge in edges:
                    rel_type = edge["relation_type"]
                    target_id = edge["target_id"]
                    
                    try:
                        # Ensure we use generic property access in MATCH
                        edge_query = f"""
                        MATCH (a), (b)
                        WHERE a.node_id = '{node_id}' AND b.node_id = '{target_id}'
                        CREATE (a)-[:{rel_type}]->(b)
                        """
                        session.run(edge_query)
                        edge_count += 1
                    except Exception as e:
                        print(f"Error creating edge {node_id} -> {target_id}: {e}")

            print(f"Successfully imported {len(nodes)} nodes and {edge_count} edges!")

if __name__ == "__main__":
    import_nodes()
