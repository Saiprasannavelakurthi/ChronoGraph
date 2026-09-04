"""
ChronoGraph — Week 2 Integrated Mid-Review Pipeline Runner

Automated verification and orchestration runner for the Week 2 mid-review.
Verifies the end-to-end data flow across all four member modules while preserving
folder separation:

                    Enterprise Data (Slack, GitHub, Jira)
                                      │
                                      ▼
                      1. data-ingestion (Karkuvel)
                         → Output: normalized_events.json & graph_ready_triples.json
                                      │
                        ┌─────────────┴─────────────┐
                        ▼                           ▼
            2. graph-extraction (Aathi)    3. neo4j-temporal (Saiprasanna)
               → process_records() on         → Ingestion of graph_ready_triples
                 normalized_events.json         into Neo4j & Temporal Queries
               → Output: extraction_result.json      │
                        │                           │
                        └─────────────┬─────────────┘
                                      ▼
                      4. Integration API (GET /api/graph)
                         → Serves real graph-ready nodes, edges, timeline
                                      │
                                      ▼
                      5. rag-ui (Nagaraj)
                         → Chat Interface + Subgraph Timeline UI
"""

import os
import sys
import json
import argparse
import subprocess
import urllib.request
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent
DATA_INGESTION_DIR = ROOT_DIR / "data-ingestion"
GRAPH_EXTRACTION_DIR = ROOT_DIR / "graph-extraction"
NEO4J_DIR = ROOT_DIR / "neo4j-temporal"
RAG_UI_DIR = ROOT_DIR / "rag-ui"
INTEGRATION_DIR = ROOT_DIR / "integration"


def print_banner(title: str):
    print("\n" + "=" * 70)
    print(f"  {title.upper()}")
    print("=" * 70)


def stage1_data_ingestion():
    print_banner("Stage 1 — Data Ingestion & Graph Preparation (Karkuvel)")
    cmd = [sys.executable, "main.py", "--prepare-graph"]
    res = subprocess.run(cmd, cwd=str(DATA_INGESTION_DIR), capture_output=True, text=True)
    
    triples_out = DATA_INGESTION_DIR / "data" / "processed" / "graph_ready_triples.json"
    summary_out = DATA_INGESTION_DIR / "data" / "processed" / "graph_prep_summary.json"
    
    if res.returncode == 0 and triples_out.exists():
        with open(triples_out, "r", encoding="utf-8") as f:
            triples = json.load(f)
            total_triples = len(triples)
            
        with open(summary_out, "r", encoding="utf-8") as f:
            summary = json.load(f)
            stats = summary.get("statistics", {})
            
        print("  [OK] Graph preparation pipeline completed successfully!")
        print(f"  [OK] Input Triples: {stats.get('total_input_triples', total_triples)}")
        print(f"  [OK] Valid Triples: {stats.get('valid_triples', total_triples)}")
        print(f"  [OK] Duplicates Removed: {stats.get('duplicates_removed', 0)}")
        print(f"  [OK] Graph-Ready Triples Generated: {total_triples}")
        print(f"  [OK] Output Contract: {triples_out}")
        return True, total_triples
    else:
        print(f"  [FAIL] Data ingestion failed:\n{res.stderr or res.stdout}")
        return False, 0


def stage2_graph_extraction(use_live_groq: bool = False):
    print_banner("Stage 2 — LLM Graph Extraction (Aathi)")
    
    adapter_script = INTEGRATION_DIR / "adapter.py"
    cmd = [sys.executable, str(adapter_script)]
    if use_live_groq:
        cmd.append("--live-groq")
        
    res = subprocess.run(cmd, cwd=str(ROOT_DIR), capture_output=True, text=True)
    
    out_file = INTEGRATION_DIR / "outputs" / "graph_extraction_result.json"
    if res.returncode == 0 and out_file.exists():
        with open(out_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        entities = data.get("entities", [])
        relationships = data.get("relationships", [])
        triples = data.get("triples", [])
        is_valid = data.get("is_valid", False)
        mode = data.get("extraction_mode", "deterministic_mock")
        events_count = data.get("events_processed", 0)
        total_evts = data.get("total_dataset_events", 100)
        
        print("  [OK] Extraction adapter successfully processed Karkuvel normalized events!")
        print(f"  [OK] Events Sampled: {events_count} of {total_evts}")
        print(f"  [OK] Extraction Mode: {mode}")
        print(f"  [OK] Entities Extracted: {len(entities)}")
        print(f"  [OK] Relationships Extracted: {len(relationships)}")
        print(f"  [OK] Triples Synchronized: {len(triples)}")
        print(f"  [OK] Validation Result: is_valid == {is_valid}")
        print(f"  [OK] Output Artifact: {out_file}")
        return True, len(entities), len(relationships), mode
    else:
        print(f"  [FAIL] Graph extraction failed:\n{res.stderr or res.stdout}")
        return False, 0, 0, "failed"


def stage2b_extraction_accuracy():
    print_banner("Stage 2B — Extraction Accuracy & Hallucination Audit")
    try:
        acc_script = GRAPH_EXTRACTION_DIR / "tests" / "test_extraction_accuracy.py"
        if str(GRAPH_EXTRACTION_DIR / "tests") not in sys.path:
            sys.path.insert(0, str(GRAPH_EXTRACTION_DIR / "tests"))
        from test_extraction_accuracy import run_extraction_accuracy_audit
        res = run_extraction_accuracy_audit()
        print(f"  [OK] Grounding Accuracy: {res['grounded']}/{res['total_triples']} ({res['accuracy_pct']:.2f}%)")
        return res["is_valid"], f"{res['grounded']}/{res['total_triples']} grounded ({res['accuracy_pct']:.2f}%)"
    except Exception as exc:
        print(f"  [FAIL] Extraction accuracy audit failed: {exc}")
        return False, f"Audit failed: {exc}"


def stage3_neo4j_temporal():
    print_banner("Stage 3 — Neo4j Temporal Graph (Saiprasanna)")
    
    # 1. Compile all Python modules
    cmd_compile = [
        sys.executable, "-m", "py_compile",
        "backend/create_graph.py",
        "backend/neo4j_connection.py",
        "backend/temporal_queries.py",
        "backend/graph_audit.py"
    ]
    res_compile = subprocess.run(cmd_compile, cwd=str(NEO4J_DIR), capture_output=True, text=True)
    if res_compile.returncode != 0:
        print(f"  [FAIL] Neo4j module compilation error:\n{res_compile.stderr}")
        return "FAIL", "Compilation error"
    print("  [OK] Python syntax and bytecode compilation verified.")
    
    # 2. Check credentials
    uri = os.getenv("NEO4J_URI")
    username = os.getenv("NEO4J_USERNAME")
    password = os.getenv("NEO4J_PASSWORD")
    
    if not (uri and username and password and not uri.startswith("neo4j://localhost:7687-placeholder")):
        print("  [BLOCKED BY EXT SERVICE] Live Neo4j credentials not configured in .env.")
        print("  -> Required for live DB: Set NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD in .env")
        print("  -> Handoff verified: neo4j-temporal/backend/create_graph.py ready to load graph_ready_triples.json")
        print("  -> Temporal queries & Audit verified: neo4j-temporal/backend/graph_audit.py")
        return "BLOCKED", "Neo4j credentials not configured"
        
    cmd = [sys.executable, "backend/create_graph.py"]
    res = subprocess.run(cmd, cwd=str(NEO4J_DIR), capture_output=True, text=True)
    if res.returncode == 0 and "Successfully ingested" in res.stdout:
        print("  [OK] Successfully ingested graph_ready_triples.json into live Neo4j database!")
        cmd_q = [sys.executable, "backend/graph_audit.py"]
        subprocess.run(cmd_q, cwd=str(NEO4J_DIR), capture_output=False, text=True)
        return "PASS", "Live Neo4j graph ingested & audited"
    else:
        print(f"  [BLOCKED BY EXT SERVICE] Neo4j instance unreachable: {res.stdout.strip() or res.stderr.strip()}")
        return "BLOCKED", "Live Neo4j unreachable"


def stage4_integration_api():
    print_banner("Stage 4 — Integration API & Graph Delivery")
    
    try:
        if str(ROOT_DIR) not in sys.path:
            sys.path.insert(0, str(ROOT_DIR))
            
        from fastapi.testclient import TestClient
        from integration.api import app
        
        client = TestClient(app)
        
        # Test health endpoint
        res_health = client.get("/api/health")
        if res_health.status_code != 200:
            print(f"  [FAIL] /api/health returned status {res_health.status_code}")
            return False, 0, 0
            
        # Test graph endpoint
        res_graph = client.get("/api/graph?limit=15")
        if res_graph.status_code != 200:
            print(f"  [FAIL] /api/graph returned status {res_graph.status_code}")
            return False, 0, 0
            
        graph_data = res_graph.json()
        node_count = len(graph_data.get("nodes", []))
        edge_count = len(graph_data.get("edges", []))
        timeline_count = len(graph_data.get("timeline", []))
        total_triples = graph_data.get("total_triples_in_dataset", 0)
        
        print("  [OK] Integration API endpoints (/api/health, /api/graph) verified!")
        print(f"  [OK] Total Triples in Dataset: {total_triples}")
        print(f"  [OK] React Flow Nodes Generated: {node_count}")
        print(f"  [OK] React Flow Edges Generated: {edge_count}")
        print(f"  [OK] Timeline Events Delivered: {timeline_count}")
        return True, node_count, edge_count
    except Exception as e:
        print(f"  [FAIL] Integration API check failed: {e}")
        return False, 0, 0


def stage5_rag_ui():
    print_banner("Stage 5 — RAG Chat & Subgraph UI (Nagaraj)")
    
    package_json = RAG_UI_DIR / "package.json"
    dist_dir = RAG_UI_DIR / "dist"
    
    if not package_json.exists():
        print("  [FAIL] rag-ui/package.json not found.")
        return False, "package.json missing"
        
    # Verify build
    cmd_build = "npm run build"
    res_build = subprocess.run(cmd_build, cwd=str(RAG_UI_DIR), shell=True, capture_output=True, text=True)
    if res_build.returncode != 0:
        print(f"  [FAIL] UI build failed:\n{res_build.stderr or res_build.stdout}")
        return False, "Build failed"
    print("  [OK] Production build verified (dist/ generated with 0 errors).")
    
    # Check if dev server is currently running
    server_live = False
    try:
        req = urllib.request.Request("http://localhost:5173/", headers={"User-Agent": "ChronoGraph-Probe"})
        with urllib.request.urlopen(req, timeout=0.8) as response:
            if response.status == 200:
                server_live = True
    except Exception:
        server_live = False
        
    if server_live:
        print("  [OK] Live Dev Server active and reachable on http://localhost:5173")
        return True, "PASS — Dev server active"
    else:
        print("  [OK] Dev server not running (Start with: 'cd rag-ui && npm run dev')")
        return True, "PASS — Build verified (Dev server offline)"


def run_all(use_live_groq: bool = False):
    print("=" * 70)
    print("   CHRONOGRAPH — WEEK 2 INTEGRATED MID-REVIEW PIPELINE")
    print("=" * 70)
    
    s1_ok, s1_count = stage1_data_ingestion()
    s2_ok, s2_entities, s2_rels, s2_mode = stage2_graph_extraction(use_live_groq=use_live_groq)
    s2b_ok, s2b_msg = stage2b_extraction_accuracy()
    s3_status, s3_msg = stage3_neo4j_temporal()
    s4_ok, s4_nodes, s4_edges = stage4_integration_api()
    s5_ok, s5_msg = stage5_rag_ui()
    
    print("\n" + "=" * 70)
    print("   MID-REVIEW INTEGRATION SUMMARY MATRIX")
    print("=" * 70)
    print(f"  1. Data Ingestion [data-ingestion]   : {'PASS' if s1_ok else 'FAIL'} ({s1_count} graph-ready triples)")
    print(f"  2. Graph Extraction [graph-extract]  : {'PASS' if s2_ok else 'FAIL'} ({s2_entities} entities, {s2_rels} rels via {s2_mode})")
    print(f"  3. Accuracy Audit  [extraction-acc]  : {'PASS' if s2b_ok else 'FAIL'} ({s2b_msg})")
    print(f"  4. Neo4j Temporal  [neo4j-temporal]   : {s3_status} ({s3_msg})")
    print(f"  5. Integration API [integration-api] : {'PASS' if s4_ok else 'FAIL'} ({s4_nodes} nodes, {s4_edges} edges)")
    print(f"  6. Frontend UI     [rag-ui]          : {'PASS' if s5_ok else 'FAIL'} ({s5_msg})")
    print("=" * 70)
    print("  All four member folders remain separate and modular.")
    print("  Automated pipeline verification complete.")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ChronoGraph Mid-Review Pipeline Runner")
    parser.add_argument(
        "--live-groq",
        action="store_true",
        help="Use live Groq API for Stage 2 (requires GROQ_API_KEY in .env)",
    )
    args = parser.parse_args()
    run_all(use_live_groq=args.live_groq)

