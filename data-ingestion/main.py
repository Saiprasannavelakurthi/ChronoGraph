"""
main.py
───────
ChronoGraph CLI entrypoint — Week 1 + Week 2 + Week 3.

Week 1 commands
───────────────
  python main.py --ingest              Run data ingestion -> normalized_events.json
  python main.py --extract             Run triple extraction -> extracted_triples.json
  python main.py --run-all             Run full Week 1 pipeline (ingest + extract)
  python main.py --export-json         Print extracted_triples.json to stdout
  python main.py --start-api           Start the FastAPI server
  python main.py --validate-dag        Validate the Airflow DAG (import check)

Week 2 commands (Karkuvel - Data Integration & Graph-Ready Pipeline)
─────────────────────────────────────────────────────────────────────
  python main.py --prepare-graph       Validate + normalize + deduplicate ->
                                       graph_ready_triples.json
  python main.py --graph-prep          Alias for --prepare-graph
  python main.py --run-week2-data      Full pipeline: ingest -> extract ->
                                       graph preparation

Week 3 commands (Karkuvel - Temporal Retrieval Preparation)
────────────────────────────────────────────────────────────
  python main.py --prepare-retrieval   Build retrieval-ready records from
                                       graph_ready_triples.json ->
                                       retrieval_ready_records.json
  python main.py --run-week3-data      Full pipeline: ingest -> extract ->
                                       graph prep -> retrieval prep

Environment
───────────
Copy .env.example -> .env and set LLM_PROVIDER (default: mock).
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
        "  Temporal GraphRAG for Enterprise Forensics - Week 1 + Week 2\n"
        "  =============================================================\n"
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
    _print_info(f"Saved -> {settings.normalized_events_path}")

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
    _print_info(f"Saved -> {settings.extracted_triples_path}")

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
# Week 2 – Graph Preparation (Karkuvel)
# ─────────────────────────────────────────────────────────────────────────────

def run_graph_prep() -> dict:
    """
    Week 2 – Graph-Ready Data Pipeline (Karkuvel's module).

    Reads: data/processed/extracted_triples.json
    Writes:
        data/processed/graph_ready_triples.json
        data/processed/graph_prep_summary.json
    """
    _print_section("Week 2: Graph-Ready Data Preparation (Karkuvel)")

    if not settings.extracted_triples_path.exists():
        _print_error(
            "extracted_triples.json not found. Run --run-all or --extract first."
        )
        sys.exit(1)

    from src.graph_prep.pipeline import GraphPrepPipeline

    pipeline = GraphPrepPipeline(
        input_path=settings.extracted_triples_path,
        output_path=settings.graph_ready_triples_path,
        summary_path=settings.graph_prep_summary_path,
    )

    result = pipeline.run()
    summary = result["summary"]
    stats = summary["statistics"]
    entities = summary["entities"]
    sources = summary["sources"]
    relations = summary["relations"]
    date_range = summary["date_range"]

    # ── Print human-readable summary ──────────────────────────────────────────
    if _RICH:
        from rich.table import Table
        _print_section("Graph Preparation Summary")

        t_stats = Table(show_header=True, header_style="bold magenta", title="Pipeline Statistics")
        t_stats.add_column("Metric", style="cyan", min_width=32)
        t_stats.add_column("Count", justify="right")
        t_stats.add_row("Total input triples",          str(stats["total_input_triples"]))
        t_stats.add_row("Valid triples",                str(stats["valid_triples"]))
        t_stats.add_row("Invalid triples",              str(stats["invalid_triples"]))
        t_stats.add_row("Duplicates removed",           str(stats["duplicates_removed"]))
        t_stats.add_row("Graph-ready triples",          str(stats["graph_ready_triples"]))
        console.print(t_stats)

        t_ent = Table(show_header=True, header_style="bold magenta", title="Unique Entities")
        t_ent.add_column("Type", style="cyan", min_width=16)
        t_ent.add_column("Count", justify="right")
        t_ent.add_row("People",       str(entities["people"]))
        t_ent.add_row("Technologies", str(entities["technologies"]))
        t_ent.add_row("Projects",     str(entities["projects"]))
        t_ent.add_row("Services",     str(entities["services"]))
        t_ent.add_row("Issues",       str(entities["issues"]))
        console.print(t_ent)

        t_src = Table(show_header=True, header_style="bold magenta", title="Source Breakdown")
        t_src.add_column("Source", style="cyan", min_width=12)
        t_src.add_column("Graph-ready triples", justify="right")
        t_src.add_row("Slack",  str(sources.get("slack", 0)))
        t_src.add_row("GitHub", str(sources.get("github", 0)))
        t_src.add_row("Jira",   str(sources.get("jira", 0)))
        console.print(t_src)

        console.print(f"\n  [cyan]Unique relation types:[/cyan] {relations['unique_relation_types']}")
        console.print(f"  [cyan]Date range:[/cyan] {date_range.get('earliest', 'N/A')} -> {date_range.get('latest', 'N/A')}")
    else:
        print("\nGraph Preparation Summary")
        print(f"  Total input triples : {stats['total_input_triples']}")
        print(f"  Valid triples       : {stats['valid_triples']}")
        print(f"  Invalid triples     : {stats['invalid_triples']}")
        print(f"  Duplicates removed  : {stats['duplicates_removed']}")
        print(f"  Graph-ready triples : {stats['graph_ready_triples']}")
        print(f"  People              : {entities['people']}")
        print(f"  Technologies        : {entities['technologies']}")
        print(f"  Projects            : {entities['projects']}")
        print(f"  Services            : {entities['services']}")
        print(f"  Issues              : {entities['issues']}")
        print(f"  Slack records       : {sources.get('slack', 0)}")
        print(f"  GitHub records      : {sources.get('github', 0)}")
        print(f"  Jira records        : {sources.get('jira', 0)}")
        print(f"  Unique relations    : {relations['unique_relation_types']}")
        print(f"  Date range          : {date_range.get('earliest', 'N/A')} -> {date_range.get('latest', 'N/A')}")

    _print_info(f"graph_ready_triples.json -> {settings.graph_ready_triples_path}")
    _print_info(f"graph_prep_summary.json  -> {settings.graph_prep_summary_path}")

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Week 3 – Retrieval Preparation (Karkuvel)
# ─────────────────────────────────────────────────────────────────────────────

def run_retrieval_prep() -> dict:
    """
    Week 3 – Temporal Retrieval Preparation (Karkuvel's module).

    Reads: data/processed/graph_ready_triples.json
    Writes:
        data/processed/retrieval_ready_records.json
        data/processed/retrieval_prep_summary.json
    """
    _print_section("Week 3: Temporal Retrieval Preparation (Karkuvel)")

    if not settings.graph_ready_triples_path.exists():
        _print_error(
            "graph_ready_triples.json not found. Run --prepare-graph or --run-week2-data first."
        )
        sys.exit(1)

    from src.retrieval.builder import RetrievalRecordBuilder

    builder = RetrievalRecordBuilder(
        input_path=settings.graph_ready_triples_path,
        output_path=settings.retrieval_ready_records_path,
        summary_path=settings.retrieval_prep_summary_path,
    )
    records, report, metadata = builder.build()

    # ── Print summary ────────────────────────────────────────────────────────
    if _RICH:
        from rich.table import Table
        _print_section("Retrieval Preparation Summary")

        t = Table(show_header=True, header_style="bold magenta", title="Build Statistics")
        t.add_column("Metric", style="cyan", min_width=28)
        t.add_column("Count", justify="right")
        t.add_row("Total graph-ready triples", str(report["total_input"]))
        t.add_row("Retrieval records built",   str(report["records_built"]))
        t.add_row("Records skipped",           str(report["records_skipped"]))
        console.print(t)

        # Source breakdown
        from collections import Counter
        source_counts = Counter(r.source for r in records)
        t_src = Table(show_header=True, header_style="bold magenta", title="Source Breakdown")
        t_src.add_column("Source", style="cyan", min_width=12)
        t_src.add_column("Records", justify="right")
        t_src.add_row("Slack",  str(source_counts.get("slack", 0)))
        t_src.add_row("GitHub", str(source_counts.get("github", 0)))
        t_src.add_row("Jira",   str(source_counts.get("jira", 0)))
        console.print(t_src)

        if records:
            dates = sorted(r.event_date for r in records)
            console.print(
                f"  [cyan]Date range:[/cyan] {dates[0]} -> {dates[-1]}"
            )
            console.print(
                f"  [cyan]Records with source_url:[/cyan] "
                f"{sum(1 for r in records if r.source_url)}"
            )

        # Execution metadata block
        t_meta = Table(show_header=True, header_style="bold magenta", title="Pipeline Execution Metadata")
        t_meta.add_column("Field", style="cyan", min_width=20)
        t_meta.add_column("Value")
        t_meta.add_row("pipeline_name",   metadata.pipeline_name)
        t_meta.add_row("input_source",    metadata.input_source)
        t_meta.add_row("total_records",   str(metadata.total_records))
        t_meta.add_row("records_built",   str(metadata.records_built))
        t_meta.add_row("skipped_records", str(metadata.skipped_records))
        t_meta.add_row("generated_at",    metadata.generated_at)
        t_meta.add_row("status",          metadata.status)
        console.print(t_meta)
    else:
        print("\nRetrieval Preparation Summary")
        print(f"  Total graph-ready triples : {report['total_input']}")
        print(f"  Retrieval records built   : {report['records_built']}")
        print(f"  Records skipped           : {report['records_skipped']}")
        if records:
            from collections import Counter
            sc = Counter(r.source for r in records)
            print(f"  Slack records             : {sc.get('slack', 0)}")
            print(f"  GitHub records            : {sc.get('github', 0)}")
            print(f"  Jira records              : {sc.get('jira', 0)}")
            dates = sorted(r.event_date for r in records)
            print(f"  Date range                : {dates[0]} -> {dates[-1]}")
        print("\nPipeline Execution Metadata")
        print(f"  pipeline_name   : {metadata.pipeline_name}")
        print(f"  input_source    : {metadata.input_source}")
        print(f"  total_records   : {metadata.total_records}")
        print(f"  records_built   : {metadata.records_built}")
        print(f"  skipped_records : {metadata.skipped_records}")
        print(f"  generated_at    : {metadata.generated_at}")
        print(f"  status          : {metadata.status}")

    _print_info(f"retrieval_ready_records.json -> {settings.retrieval_ready_records_path}")
    _print_info(f"retrieval_prep_summary.json  -> {settings.retrieval_prep_summary_path}")
    return report


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="chronograph",
        description="ChronoGraph CLI – Week 1 + Week 2 + Week 3 (Temporal Retrieval Preparation)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Week 1 examples:
  python main.py --run-all                      Full Week 1 pipeline (ingest + extract)
  python main.py --ingest                       Only load & normalise data
  python main.py --extract                      Only extract triples
  python main.py --export-json                  Print extracted_triples.json to stdout
  python main.py --validate-dag                 Check Airflow DAG syntax
  python main.py --start-api                    Start FastAPI server on :8000

Week 2 examples (Karkuvel – Graph-Ready Data Pipeline):
  python main.py --prepare-graph                Validate + normalize + deduplicate triples
  python main.py --graph-prep                   Alias for --prepare-graph
  python main.py --run-week2-data               Full pipeline: ingest -> extract -> graph prep

Week 3 examples (Karkuvel – Temporal Retrieval Preparation):
  python main.py --prepare-retrieval            Build retrieval-ready records from graph_ready_triples.json
  python main.py --run-week3-data               Full pipeline: ingest -> extract -> graph prep -> retrieval prep

LLM modes (set in .env or environment):
  LLM_PROVIDER=groq     -> Groq Cloud API (llama-3.1-8b-instant, default)
  LLM_PROVIDER=ollama   -> Ollama + Llama3 local inference
  LLM_PROVIDER=openai   -> OpenAI API (requires OPENAI_API_KEY)
  LLM_PROVIDER=mock     -> Heuristic fallback (no external services required)
        """,
    )

    group = parser.add_mutually_exclusive_group(required=True)
    # ── Week 1 commands ──────────────────────────────────────────────────────
    group.add_argument("--ingest", action="store_true", help="Run ingestion pipeline only")
    group.add_argument("--extract", action="store_true", help="Run extraction pipeline only")
    group.add_argument("--run-all", action="store_true", help="Run full ingestion + extraction pipeline")
    group.add_argument("--export-json", action="store_true", help="Print extracted_triples.json to stdout")
    group.add_argument("--start-api", action="store_true", help="Start FastAPI REST server")
    group.add_argument("--validate-dag", action="store_true", help="Validate Airflow DAG import")
    # ── Week 2 commands (Karkuvel) ────────────────────────────────────────────
    group.add_argument(
        "--prepare-graph",
        action="store_true",
        help="Week 2: Validate, normalize & deduplicate triples -> graph_ready_triples.json",
    )
    group.add_argument(
        "--graph-prep",
        action="store_true",
        help="Alias for --prepare-graph",
    )
    group.add_argument(
        "--run-week2-data",
        action="store_true",
        help="Week 2: Full pipeline — ingest -> extract -> graph preparation",
    )
    # ── Week 3 commands (Karkuvel) ────────────────────────────────────────────
    group.add_argument(
        "--prepare-retrieval",
        action="store_true",
        help="Week 3: Build retrieval-ready records from graph_ready_triples.json",
    )
    group.add_argument(
        "--run-week3-data",
        action="store_true",
        help="Week 3: Full pipeline — ingest -> extract -> graph prep -> retrieval prep",
    )

    args = parser.parse_args()

    _print_banner()

    # ── Week 1 dispatching ───────────────────────────────────────────────────
    if args.ingest:
        run_ingest()

    elif args.extract:
        run_extract()

    elif args.run_all:
        events = run_ingest()
        run_extract(events)
        _print_section("Week 1 Pipeline Complete")
        _print_info(f"normalized_events.json -> {settings.normalized_events_path}")
        _print_info(f"extracted_triples.json -> {settings.extracted_triples_path}")
        _print_info("Run '--prepare-graph' to execute Week 2 graph preparation.")

    elif args.export_json:
        export_json()

    elif args.start_api:
        start_api()

    elif args.validate_dag:
        validate_dag()

    # ── Week 2 dispatching (Karkuvel) ────────────────────────────────────────
    elif args.prepare_graph or args.graph_prep:
        run_graph_prep()
        _print_section("Week 2 Graph Preparation Complete")

    elif args.run_week2_data:
        events = run_ingest()
        run_extract(events)
        run_graph_prep()
        _print_section("Week 2 Full Pipeline Complete")
        _print_info(f"normalized_events.json   -> {settings.normalized_events_path}")
        _print_info(f"extracted_triples.json   -> {settings.extracted_triples_path}")
        _print_info(f"graph_ready_triples.json -> {settings.graph_ready_triples_path}")
        _print_info(f"graph_prep_summary.json  -> {settings.graph_prep_summary_path}")

    # ── Week 3 dispatching (Karkuvel) ────────────────────────────────────────
    elif args.prepare_retrieval:
        run_retrieval_prep()
        _print_section("Week 3 Retrieval Preparation Complete")

    elif args.run_week3_data:
        events = run_ingest()
        run_extract(events)
        run_graph_prep()
        run_retrieval_prep()
        _print_section("Week 3 Full Pipeline Complete")
        _print_info(f"normalized_events.json         -> {settings.normalized_events_path}")
        _print_info(f"extracted_triples.json         -> {settings.extracted_triples_path}")
        _print_info(f"graph_ready_triples.json       -> {settings.graph_ready_triples_path}")
        _print_info(f"graph_prep_summary.json        -> {settings.graph_prep_summary_path}")
        _print_info(f"retrieval_ready_records.json   -> {settings.retrieval_ready_records_path}")
        _print_info(f"retrieval_prep_summary.json    -> {settings.retrieval_prep_summary_path}")


if __name__ == "__main__":
    main()
