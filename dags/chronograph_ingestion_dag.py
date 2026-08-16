"""
dags/chronograph_ingestion_dag.py
──────────────────────────────────
Airflow DAG for ChronoGraph Week 1 + Week 2 (Karkuvel's graph preparation).

Pipeline
────────

start_task
    │
    ▼
load_slack_task          ← SlackLoader: reads slack_history.json
    │
    ▼
load_github_task         ← GitHubLoader: reads github_prs.json
    │
    ▼
load_jira_task           ← JiraLoader: reads jira_tickets.json
    │
    ▼
preprocess_normalize_task ← IngestionPipeline: merge + clean + normalise
    │
    ▼
save_normalized_events_task ← writes data/processed/normalized_events.json
    │
    ▼
extract_triples_task     ← TemporalTripleExtractor: LLM or fallback
    │
    ▼
prepare_graph_data_task  ← Karkuvel: validate + normalize + deduplicate
    │                        writes graph_ready_triples.json
    ▼
end_task

Week 1 scope:
  ✅ All ingestion tasks
  ✅ Preprocessing/normalisation
  ✅ Triple extraction

Week 2 scope (Karkuvel – Data Integration & Graph-Ready Pipeline):
  ✅ prepare_graph_data_task: validate, normalize & deduplicate triples
  ✅ Outputs graph_ready_triples.json for Saiprasanna's Neo4j module

Out of scope (other team members):
  ❌ Neo4j graph construction (Saiprasanna – Week 2)
  ❌ Temporal RAG retrieval (Vembarasan/Nagarajan – Week 3+)
  ❌ React/UI/visualization (Vembarasan/Nagarajan)

Setup
─────
Install Airflow with the Python version constraint:

  AIRFLOW_VERSION=2.8.0
  PYTHON_VERSION=3.10
  pip install "apache-airflow==${AIRFLOW_VERSION}" \
    --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt"

  export AIRFLOW_HOME=$(pwd)/airflow
  airflow db init
  airflow standalone   # starts web server + scheduler on localhost:8080

Then copy this file to $AIRFLOW_HOME/dags/ or set AIRFLOW__CORE__DAGS_FOLDER
to point to the /dags directory in this project.

Run a manual trigger:
  airflow dags trigger chronograph_week1_ingestion
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# ── Ensure the project root is on sys.path so src.* imports work ──────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ── Airflow imports ───────────────────────────────────────────────────────────
try:
    from airflow import DAG
    from airflow.operators.python import PythonOperator
    from airflow.operators.empty import EmptyOperator
    _AIRFLOW_AVAILABLE = True
except ImportError:
    _AIRFLOW_AVAILABLE = False
    # Provide stubs so the module can still be imported for syntax validation
    # and for running the pipeline manually via the standalone runner below.
    class DAG:  # type: ignore
        def __init__(self, dag_id: str = "", *a, **kw):
            self.dag_id = dag_id or (a[0] if a else "")
        def __enter__(self): return self
        def __exit__(self, *a): pass

    class PythonOperator:  # type: ignore
        def __init__(self, *a, **kw):
            self.task_id = kw.get("task_id", "")
        def __rshift__(self, other): return other

    class EmptyOperator:  # type: ignore
        def __init__(self, *a, **kw):
            self.task_id = kw.get("task_id", "")
        def __rshift__(self, other): return other

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Default DAG arguments
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_ARGS = {
    "owner": "chronograph",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=2),
}


# ─────────────────────────────────────────────────────────────────────────────
# Task functions
# ─────────────────────────────────────────────────────────────────────────────


def _get_settings():
    """Import settings inside task functions to avoid Airflow serialisation issues."""
    from config.settings import settings
    return settings


def task_load_slack(**context) -> dict:
    """
    Task 1: Load Slack data.

    Reads slack_history.json and returns a count of raw records for XCom.
    The actual conversion to RawEvents happens in the preprocessing task.
    """
    settings = _get_settings()
    from src.ingestion.slack_loader import SlackLoader

    loader = SlackLoader(settings.slack_raw_path)
    raw_records = loader.load()
    event_count = len(raw_records)

    logger.info("Airflow [load_slack]: loaded %d raw Slack records", event_count)
    return {"source": "slack", "record_count": event_count}


def task_load_github(**context) -> dict:
    """
    Task 2: Load GitHub data.

    Reads github_prs.json and returns a count of raw records for XCom.
    """
    settings = _get_settings()
    from src.ingestion.github_loader import GitHubLoader

    loader = GitHubLoader(settings.github_raw_path)
    raw_records = loader.load()
    event_count = len(raw_records)

    logger.info("Airflow [load_github]: loaded %d raw GitHub records", event_count)
    return {"source": "github", "record_count": event_count}


def task_load_jira(**context) -> dict:
    """
    Task 3: Load Jira data.

    Reads jira_tickets.json and returns a count of raw records for XCom.
    """
    settings = _get_settings()
    from src.ingestion.jira_loader import JiraLoader

    loader = JiraLoader(settings.jira_raw_path)
    raw_records = loader.load()
    event_count = len(raw_records)

    logger.info("Airflow [load_jira]: loaded %d raw Jira records", event_count)
    return {"source": "jira", "record_count": event_count}


def task_preprocess_normalize(**context) -> dict:
    """
    Task 4 + 5: Preprocess & normalise all sources, then save.

    Runs the full IngestionPipeline which:
      - Loads Slack, GitHub, Jira
      - Merges into one event list
      - Normalises timestamps and text
      - Saves normalized_events.json
    """
    settings = _get_settings()
    from src.ingestion.pipeline import IngestionPipeline

    pipeline = IngestionPipeline(
        slack_path=settings.slack_raw_path,
        github_path=settings.github_raw_path,
        jira_path=settings.jira_raw_path,
        output_path=settings.normalized_events_path,
        max_events=settings.extraction_max_events,
    )
    events = pipeline.run()

    counts = {}
    for evt in events:
        counts[evt.source.value] = counts.get(evt.source.value, 0) + 1

    logger.info(
        "Airflow [preprocess_normalize]: %d events normalised – %s",
        len(events), counts,
    )
    return {
        "total_events": len(events),
        "events_by_source": counts,
        "output_path": str(settings.normalized_events_path),
    }


def task_extract_triples(**context) -> dict:
    """
    Task 6: Extract Entity → [RELATION] → Entity triples.

    Reads normalized_events.json, runs the TemporalTripleExtractor
    (LLM or fallback), and writes extracted_triples.json.
    """
    settings = _get_settings()
    from src.extraction.extractor import TemporalTripleExtractor
    from src.schemas.graph import RawEvent, Triple

    # Load normalised events
    if not settings.normalized_events_path.exists():
        raise FileNotFoundError(
            f"normalized_events.json not found at {settings.normalized_events_path}. "
            "Ensure preprocess_normalize task ran successfully."
        )

    with open(settings.normalized_events_path, "r", encoding="utf-8") as fh:
        raw_list = json.load(fh)
    events = [RawEvent(**item) for item in raw_list]

    extractor = TemporalTripleExtractor(
        llm_provider=settings.llm_provider,
        ollama_base_url=settings.ollama_base_url,
        ollama_model=settings.ollama_model,
        openai_api_key=settings.openai_api_key,
        openai_model=settings.openai_model,
        groq_api_key=settings.groq_api_key,
        groq_model=settings.groq_model,
        min_confidence=settings.extraction_min_confidence,
        auto_fallback=True,
    )

    results = extractor.extract_batch(events)
    all_triples: list[Triple] = []
    for result in results:
        all_triples.extend(result.triples)

    # Persist to disk
    settings.processed_data_dir.mkdir(parents=True, exist_ok=True)
    with open(settings.extracted_triples_path, "w", encoding="utf-8") as fh:
        json.dump(
            [t.to_neo4j_dict() for t in all_triples],
            fh,
            indent=2,
            ensure_ascii=False,
            default=str,
        )

    mode_counts: dict = {}
    for t in all_triples:
        mode_counts[t.extraction_mode.value] = mode_counts.get(t.extraction_mode.value, 0) + 1

    logger.info(
        "Airflow [extract_triples]: %d triples extracted, modes=%s",
        len(all_triples), mode_counts,
    )
    return {
        "total_triples": len(all_triples),
        "triples_by_mode": mode_counts,
        "output_path": str(settings.extracted_triples_path),
    }


def task_prepare_graph_data(**context) -> dict:
    """
    Week 2 Task (Karkuvel): Validate, normalize & deduplicate extracted triples.

    Reads  : data/processed/extracted_triples.json
    Writes :
        data/processed/graph_ready_triples.json  (Neo4j-ready contract)
        data/processed/graph_prep_summary.json   (stats + audit log)

    This task does NOT connect to Neo4j.  Its output file is the
    integration contract for Saiprasanna's Neo4j loading module.
    """
    settings = _get_settings()
    from src.graph_prep.pipeline import GraphPrepPipeline

    if not settings.extracted_triples_path.exists():
        raise FileNotFoundError(
            f"extracted_triples.json not found at {settings.extracted_triples_path}. "
            "Ensure extract_triples task ran successfully."
        )

    pipeline = GraphPrepPipeline(
        input_path=settings.extracted_triples_path,
        output_path=settings.graph_ready_triples_path,
        summary_path=settings.graph_prep_summary_path,
    )
    result = pipeline.run()
    stats = result["summary"]["statistics"]

    logger.info(
        "Airflow [prepare_graph_data]: %d input → %d graph-ready (%d duplicates removed, %d invalid)",
        stats["total_input_triples"],
        stats["graph_ready_triples"],
        stats["duplicates_removed"],
        stats["invalid_triples"],
    )
    return {
        "total_input_triples": stats["total_input_triples"],
        "graph_ready_triples": stats["graph_ready_triples"],
        "duplicates_removed": stats["duplicates_removed"],
        "invalid_triples": stats["invalid_triples"],
        "output_path": str(settings.graph_ready_triples_path),
        "summary_path": str(settings.graph_prep_summary_path),
    }


# ─────────────────────────────────────────────────────────────────────────────
# DAG definition
# ─────────────────────────────────────────────────────────────────────────────

with DAG(
    dag_id="chronograph_week1_ingestion",
    default_args=DEFAULT_ARGS,
    description=(
        "ChronoGraph Week 1 + Week 2 (Karkuvel): Ingest enterprise data "
        "(Slack/GitHub/Jira), normalise events, extract temporal knowledge-graph "
        "triples, then validate/normalise/deduplicate for graph-ready output."
    ),
    schedule_interval="@daily",          # run daily; trigger manually for demo
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["chronograph", "week1", "week2", "ingestion", "extraction", "graph-prep"],
    max_active_runs=1,
) as dag:

    # ── Sentinel start ────────────────────────────────────────────────────────
    start = EmptyOperator(task_id="start")

    # ── Load tasks ────────────────────────────────────────────────────────────
    load_slack = PythonOperator(
        task_id="load_slack",
        python_callable=task_load_slack,
    )

    load_github = PythonOperator(
        task_id="load_github",
        python_callable=task_load_github,
    )

    load_jira = PythonOperator(
        task_id="load_jira",
        python_callable=task_load_jira,
    )

    # ── Preprocess + save normalised events ───────────────────────────────────
    preprocess = PythonOperator(
        task_id="preprocess_normalize",
        python_callable=task_preprocess_normalize,
    )

    # ── Extract triples ───────────────────────────────────────────────────────
    extract = PythonOperator(
        task_id="extract_triples",
        python_callable=task_extract_triples,
    )

    # ── Sentinel end ──────────────────────────────────────────────────────────
    end = EmptyOperator(task_id="end")

    # ── Pipeline wiring ───────────────────────────────────────────────────────
    # start → load_slack → load_github → load_jira → preprocess → extract → end
    start >> load_slack >> load_github >> load_jira >> preprocess >> extract >> end


# ─────────────────────────────────────────────────────────────────────────────
# Standalone runner (use when Airflow is not installed)
# ─────────────────────────────────────────────────────────────────────────────

def run_pipeline_standalone() -> None:
    """
    Run the full pipeline sequentially without Airflow.

    Used by ``python main.py --run-all`` and for CI/CD environments
    where Airflow may not be installed.
    """
    logger.info("=== ChronoGraph Week 1 + Week 2 Pipeline (Standalone) ===")

    steps = [
        ("load_slack",           task_load_slack),
        ("load_github",          task_load_github),
        ("load_jira",            task_load_jira),
        ("preprocess_normalize", task_preprocess_normalize),
        ("extract_triples",      task_extract_triples),
        ("prepare_graph_data",   task_prepare_graph_data),   # Week 2 (Karkuvel)
    ]

    results = {}
    for name, fn in steps:
        logger.info("→ Running step: %s", name)
        try:
            result = fn()
            results[name] = result
            logger.info("  ✓ %s: %s", name, result)
        except Exception as exc:
            logger.error("  ✗ %s FAILED: %s", name, exc)
            raise

    logger.info("=== Pipeline complete ===")
    return results


if __name__ == "__main__":
    # Allow running directly: python dags/chronograph_ingestion_dag.py
    logging.basicConfig(level=logging.INFO)
    run_pipeline_standalone()
