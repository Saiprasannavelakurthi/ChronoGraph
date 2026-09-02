"""
backend/benchmark_queries.py
──────────────────────────────
Week 4 — Performance Tuning: prove the optimization worked with real numbers.

Runs each of the module's actual temporal queries N times against the
live Neo4j Aura instance, reports min/max/avg latency in milliseconds,
and (optionally) prints the query plan via PROFILE so you can see
"NodeByLabelScan" turn into "NodeIndexSeek" after optimize_graph.py runs.

Usage:
    python backend/benchmark_queries.py            # timing only
    python backend/benchmark_queries.py --profile  # also show query plans
"""

import sys
import time
import statistics

from neo4j_connection import driver, DATABASE
from temporal_queries import (
    get_all_events,
    get_events_after,
    get_person_history,
    get_events_between,
    get_technology_history,
)

RUNS_PER_QUERY = 5

# (label, callable, args) — args pulled from real ingestion data so this
# benchmarks realistic queries, not synthetic worst-cases.
BENCHMARKS = [
    ("get_all_events", get_all_events, []),
    ("get_events_after", get_events_after, ["2023-01-01"]),
    ("get_person_history", get_person_history, ["arun_sharma"]),
    ("get_events_between", get_events_between, ["2023-03-01", "2023-06-01"]),
    ("get_technology_history", get_technology_history, ["gcp"]),
]


def time_query(fn, args):
    start = time.perf_counter()
    fn(*args)
    return (time.perf_counter() - start) * 1000  # ms


def run_benchmarks():
    print(f"{'Query':<28} {'Min (ms)':>10} {'Avg (ms)':>10} {'Max (ms)':>10}")
    print("-" * 62)

    results = {}
    for name, fn, args in BENCHMARKS:
        timings = []
        for _ in range(RUNS_PER_QUERY):
            try:
                timings.append(time_query(fn, args))
            except Exception as e:
                print(f"{name:<28} FAILED: {e}")
                break
        else:
            results[name] = timings
            print(
                f"{name:<28} {min(timings):>10.2f} "
                f"{statistics.mean(timings):>10.2f} {max(timings):>10.2f}"
            )

    return results


def show_query_plans():
    """
    PROFILE reveals the actual execution plan Neo4j chose. Before
    optimize_graph.py: expect AllNodesScan / NodeByLabelScan with no
    filter pushed down. After: expect NodeIndexSeek on the name/timestamp
    indexes we created.
    """
    sample_queries = {
        "person_history": (
            """
            PROFILE
            MATCH (a)-[r]->(b)
            WHERE a.name = $person_name AND r.timestamp IS NOT NULL
            RETURN a.name, type(r), b.name, r.timestamp
            """,
            {"person_name": "arun_sharma"},
        ),
        "all_events": (
            """
            PROFILE
            MATCH (a)-[r]->(b)
            WHERE r.timestamp IS NOT NULL
            RETURN a.name, type(r), b.name, r.timestamp
            ORDER BY r.timestamp
            """,
            {},
        ),
    }

    with driver.session(database=DATABASE) as session:
        for name, (query, params) in sample_queries.items():
            print(f"\n--- Query plan: {name} ---")
            result = session.run(query, params)
            summary = result.consume()
            plan = summary.profile
            _print_plan(plan)


def _print_plan(plan, depth=0):
    if not plan:
        return
    op = plan.get("operatorType", "?")
    rows = plan.get("rows", "?")
    db_hits = plan.get("dbHits", "?")
    print("  " * depth + f"{op} (rows={rows}, dbHits={db_hits})")
    for child in plan.get("children", []):
        _print_plan(child, depth + 1)


if __name__ == "__main__":
    print("Running query benchmarks against live Neo4j Aura instance...\n")
    run_benchmarks()

    if "--profile" in sys.argv:
        show_query_plans()

    driver.close()
