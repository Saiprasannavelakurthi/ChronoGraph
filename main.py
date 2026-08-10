"""
main.py
───────
ChronoGraph Week 1 – CLI entrypoint.

Usage
─────
  python main.py --ingest          Run data ingestion → normalized_events.json
  python main.py --extract         Run triple extraction → extracted_triples.json
  python main.py --run-all         Run full pipeline (ingest + extract)
  python main.py --export-json     Print extracted_triples.json to stdout
  python main.py --start-api       Start the FastAPI server
  python main.py --validate-dag    Validate the Airflow DAG (import check)

Environment
───────────
Copy .env.example → .env and set LLM_PROVIDER (default: mock).
With LLM_PROVIDER=mock no external services are required.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# ── Ensure project root is on sys.path ────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config.settings import settings
from src.extraction.extractor import TemporalTripleExtractor
from src.ingestion.pipeline import IngestionPipeline
from src.schemas.graph import RawEvent, Triple

# Rich for pretty output (degrades gracefully if not installed)
try:
    from rich.console import Console
    from rich.table import Table
    from rich import print as rprint
    # Force UTF-8 safe, no emoji output on Windows to avoid CP1252 codec errors
    console = Console(highlight=False, emoji=False, markup=True)
    _RICH = True
except ImportError:
    _RICH = False
    console = None  # type: ignore

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _print_banner() -> None:
    banner = (
        "\n"
        "  ChronoGraph\n"
        "  Temporal GraphRAG for Enterprise Forensics - Week 1\n"
        "  =====================================================\n"
    )
    if _RICH:
        console.print(f"[bold cyan]{banner}[/bold cyan]")
    else:
        print(banner)


def _print_section(title: str) -> None:
    sep = "-" * 60
    if _RICH:
        console.print(f"\n[bold green]{sep}[/bold green]")
        console.print(f"[bold green]  {title}[/bold green]")
        console.print(f"[bold green]{sep}[/bold green]")
    else:
        print(f"\n{sep}\n  {title}\n{sep}")


def _print_info(msg: str) -> None:
    if _RICH:
        console.print(f"[cyan]  [OK] {msg}[/cyan]")
    else:
        print(f"  [OK] {msg}")


def _print_error(msg: str) -> None:
    if _RICH:
        console.print(f"[red]  [ERR] {msg}[/red]")
    else:
        print(f"  [ERR] {msg}", file=sys.stderr)


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline steps
# ─────────────────────────────────────────────────────────────────────────────

def run_ingest() -> list[RawEvent]:
    """Execute the data ingestion pipeline."""
    _print_section("Step 1: Data Ingestion")

    pipeline = IngestionPipeline(
        slack_path=settings.slack_raw_path,
        github_path=settings.github_raw_path,
        jira_path=settings.jira_raw_path,
        output_path=settings.normalized_events_path,
        max_events=settings.extraction_max_events,
    )
    events = pipeline.run()

    counts: dict[str, int] = {}
    for evt in events:
        counts[evt.source.value] = counts.get(evt.source.value, 0) + 1

    _print_info(f"Total events loaded: {len(events)}")
    for source, count in counts.items():
        _print_info(f"  {source}: {count} events")
    _print_info(f"Saved → {settings.normalized_events_path}")

    return events


def run_extract(events: list[RawEvent] | None = None) -> list[Triple]:
    """Execute the triple extraction pipeline."""
    _print_section("Step 2: Triple Extraction")
    _print_info(f"LLM provider: {settings.llm_provider}")

    # Load from disk if events not passed directly
    if events is None:
        if not settings.normalized_events_path.exists():
            _print_error("normalized_events.json not found. Run --ingest first.")
            sys.exit(1)
        with open(settings.normalized_events_path, "r", encoding="utf-8") as fh:
            raw_list = json.load(fh)
        events = [RawEvent(**item) for item in raw_list]
        _print_info(f"Loaded {len(events)} events from {settings.normalized_events_path}")

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

    # Save output
    settings.processed_data_dir.mkdir(parents=True, exist_ok=True)
    with open(settings.extracted_triples_path, "w", encoding="utf-8") as fh:
        json.dump(
            [t.to_neo4j_dict() for t in all_triples],
            fh,
            indent=2,
            ensure_ascii=False,
            default=str,
        )

    # Summarise
    mode_counts: dict[str, int] = {}
    for t in all_triples:
        mode_counts[t.extraction_mode.value] = mode_counts.get(t.extraction_mode.value, 0) + 1

    _print_info(f"Total triples extracted: {len(all_triples)}")
    for mode, count in mode_counts.items():
        _print_info(f"  {mode}: {count} triples")
    _print_info(f"Saved → {settings.extracted_triples_path}")

    # Show a sample triple in a rich table
    if all_triples and _RICH:
        _print_section("Sample Extracted Triple")
        t = all_triples[0]
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Field", style="cyan", min_width=14)
        table.add_column("Value")
        table.add_row("subject", t.subject)
        table.add_row("relation", t.relation)
        table.add_row("object", t.object)
        table.add_row("timestamp", t.timestamp.isoformat())
        table.add_row("source", t.source.value)
        table.add_row("source_id", t.source_id)
        table.add_row("confidence", str(t.confidence))
        table.add_row("extraction_mode", t.extraction_mode.value)
        table.add_row("evidence", t.evidence[:120] + ("…" if len(t.evidence) > 120 else ""))
        console.print(table)
    elif all_triples:
        t = all_triples[0]
        print("\nSample triple:")
        print(json.dumps(t.to_neo4j_dict(), indent=2, default=str))

    return all_triples


def export_json() -> None:
    """Print extracted_triples.json to stdout."""
    if not settings.extracted_triples_path.exists():
        _print_error("extracted_triples.json not found. Run --extract or --run-all first.")
        sys.exit(1)
    with open(settings.extracted_triples_path, "r", encoding="utf-8") as fh:
        print(fh.read())


def validate_dag() -> None:
    """Validate the Airflow DAG by importing it."""
    _print_section("Airflow DAG Validation")
    try:
        import importlib.util
        dag_path = _PROJECT_ROOT / "dags" / "chronograph_ingestion_dag.py"
        spec = importlib.util.spec_from_file_location("chronograph_dag", dag_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _print_info("DAG module imported successfully: chronograph_week1_ingestion")
        dag_obj = getattr(module, "dag", None)
        dag_id = getattr(dag_obj, "dag_id", None)
        if dag_id:
            _print_info(f"DAG ID: {dag_id}")
        if hasattr(module, "run_pipeline_standalone"):
            _print_info("Standalone runner available: module.run_pipeline_standalone()")
    except ImportError as exc:
        if "airflow" in str(exc).lower():
            _print_info("Airflow not installed – DAG module uses stub classes (expected).")
            _print_info("DAG structure is syntactically valid.")
        else:
            _print_error(f"DAG import error: {exc}")
    except Exception as exc:
        _print_error(f"DAG validation error: {exc}")
        raise


def start_api() -> None:
    """Start the FastAPI server."""
    _print_section("Starting FastAPI Server")
    try:
        import uvicorn
        _print_info(f"Server: http://{settings.api_host}:{settings.api_port}")
        _print_info("Docs:   http://localhost:8000/docs")
        _print_info("Health: http://localhost:8000/api/v1/health")
        uvicorn.run(
            "src.api.app:app",
            host=settings.api_host,
            port=settings.api_port,
            reload=settings.api_reload,
            log_level=settings.log_level.lower(),
        )
    except ImportError:
        _print_error("uvicorn not installed. Run: pip install uvicorn[standard]")
        sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="chronograph",
        description="ChronoGraph Week 1 – Temporal GraphRAG for Enterprise Forensics",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --run-all                      Full pipeline with fallback extraction
  python main.py --ingest                       Only load & normalise data
  python main.py --extract                      Only extract triples
  python main.py --export-json                  Print extracted_triples.json to stdout
  python main.py --validate-dag                 Check Airflow DAG syntax
  python main.py --start-api                    Start FastAPI server on :8000

LLM modes (set in .env or environment):
  LLM_PROVIDER=groq     → Groq Cloud API (llama-3.1-8b-instant, default)
  LLM_PROVIDER=ollama   → Ollama + Llama3 local inference
  LLM_PROVIDER=openai   → OpenAI API (requires OPENAI_API_KEY)
  LLM_PROVIDER=mock     → Heuristic fallback (no external services required)
        """,
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ingest", action="store_true", help="Run ingestion pipeline only")
    group.add_argument("--extract", action="store_true", help="Run extraction pipeline only")
    group.add_argument("--run-all", action="store_true", help="Run full ingestion + extraction pipeline")
    group.add_argument("--export-json", action="store_true", help="Print extracted_triples.json to stdout")
    group.add_argument("--start-api", action="store_true", help="Start FastAPI REST server")
    group.add_argument("--validate-dag", action="store_true", help="Validate Airflow DAG import")

    args = parser.parse_args()

    _print_banner()

    if args.ingest:
        run_ingest()

    elif args.extract:
        run_extract()

    elif args.run_all:
        events = run_ingest()
        run_extract(events)
        _print_section("Week 1 Pipeline Complete")
        _print_info(f"normalized_events.json → {settings.normalized_events_path}")
        _print_info(f"extracted_triples.json → {settings.extracted_triples_path}")
        _print_info("Week 2 can now consume extracted_triples.json for Neo4j ingestion.")

    elif args.export_json:
        export_json()

    elif args.start_api:
        start_api()

    elif args.validate_dag:
        validate_dag()


if __name__ == "__main__":
    main()
