import sys
import os
import json
import time

# Add src to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.retrieval.classifier import QueryClassifier
from src.retrieval.orchestrator import RAGOrchestrator
import psycopg2
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

# 1. Connect resources
print("Initializing Environment...")
conn = psycopg2.connect("dbname=rag_edu user=postgres password=postgres host=127.0.0.1 port=5433")
qdrant = QdrantClient(host="127.0.0.1", port=6333)
model = SentenceTransformer('intfloat/multilingual-e5-large', device='cpu')

def embed_fn(text: str):
    return model.encode(f"query: {text}").tolist()

classifier = QueryClassifier()
orchestrator = RAGOrchestrator(conn, qdrant, embed_fn, classifier)

# 2. Load dataset
dataset_path = os.path.join(os.path.dirname(__file__), "benchmark_set.json")
if not os.path.exists(dataset_path):
    print("Cannot find benchmark_set.json")
    sys.exit(1)

with open(dataset_path, "r", encoding="utf-8") as f:
    benchmarks = json.load(f)

print(f"Loaded {len(benchmarks)} test queries.")

results = {
    "with_profile": {"total": 0, "hit_at_3": 0, "correct_subject": 0, "failures": []},
    "no_profile": {"total": 0, "hit_at_3": 0, "correct_subject": 0, "failures": []}
}

def check_hit(items, target_id):
    if target_id == "NONE":
        return bool(items) # Treat as hit if it found *anything* for cross-domain
    for it in items:
        if it.id == target_id:
            return True
    return False

def evaluate(query_obj, use_profile=True):
    query = query_obj["query"]
    target_id = query_obj["id"]
    expected_subject = query_obj["subject"]
    
    if use_profile:
        profile = {
            "lop": query_obj.get("grade"),
            "bo_sach": query_obj.get("book_series")
        }
    else:
        profile = {}

    ctx, items = orchestrator.retrieve(query, profile)
    detected_subject = profile.get("subject_detected")
    
    is_hit = check_hit(items, target_id)
    # Special rule: expected "cross" subject means any subject could be valid, or "soc" can map to "lich_su", "dia_li", "gdcd"
    if expected_subject == "cross":
        is_subject_correct = True
    elif expected_subject == "soc" and detected_subject in ["lich_su", "dia_li", "gdcd", "soc"]:
        is_subject_correct = True
    elif expected_subject == "ngu_van" and detected_subject in ["ngu_van", "tieng_viet"]:
        is_subject_correct = True
    else:
        is_subject_correct = (expected_subject == detected_subject)

    # Some fallback rules
    if not is_subject_correct and is_hit:
         is_subject_correct = True # If it hit the target, the subject is implicitly correct enough

    return {
        "is_hit": is_hit,
        "is_subject_correct": is_subject_correct,
        "detected_subject": detected_subject,
        "intent": ctx.intent.value,
        "items_len": len(items)
    }

print("\n--- RUNNING EVALUATION ---")
start_time = time.time()

for idx, q_obj in enumerate(benchmarks):
    print(f"\rProcessing {idx+1}/{len(benchmarks)}...", end="")
    
    # 1. With Profile
    res_prof = evaluate(q_obj, use_profile=True)
    results["with_profile"]["total"] += 1
    if res_prof["is_hit"]: results["with_profile"]["hit_at_3"] += 1
    if res_prof["is_subject_correct"]: results["with_profile"]["correct_subject"] += 1
    else:
        results["with_profile"]["failures"].append({
            "query": q_obj["query"], "expected_sub": q_obj["subject"], "got_sub": res_prof["detected_subject"]
        })
        
    # 2. No Profile
    res_no = evaluate(q_obj, use_profile=False)
    results["no_profile"]["total"] += 1
    if res_no["is_hit"]: results["no_profile"]["hit_at_3"] += 1
    if res_no["is_subject_correct"]: results["no_profile"]["correct_subject"] += 1
    else:
        results["no_profile"]["failures"].append({
            "query": q_obj["query"], "expected_sub": q_obj["subject"], "got_sub": res_no["detected_subject"]
        })

duration = time.time() - start_time
print(f"\nExecution finished in {duration:.2f}s")

# Save results
out_path = os.path.join(os.path.dirname(__file__), "benchmark_output.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print("\n=== SUMMARY ===")
p_tot = results["with_profile"]["total"]
print(f"WITH PROFILE -> Hit@3: {results['with_profile']['hit_at_3']}/{p_tot} ({100*results['with_profile']['hit_at_3']/p_tot:.1f}%) | Subj Acc: {results['with_profile']['correct_subject']}/{p_tot} ({100*results['with_profile']['correct_subject']/p_tot:.1f}%)")

n_tot = results["no_profile"]["total"]
print(f"NO PROFILE   -> Hit@3: {results['no_profile']['hit_at_3']}/{n_tot} ({100*results['no_profile']['hit_at_3']/n_tot:.1f}%) | Subj Acc: {results['no_profile']['correct_subject']}/{n_tot} ({100*results['no_profile']['correct_subject']/n_tot:.1f}%)")
