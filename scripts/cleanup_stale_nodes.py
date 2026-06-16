#!/usr/bin/env python3
"""Delete stale uncommitted nodes from the graph database.

Nodes that were saved (persisted to DB) but never committed indicate a failed
build operation. This script finds and removes them based on saved_at age.

Usage:
    python scripts/cleanup_stale_nodes.py
    python scripts/cleanup_stale_nodes.py --max-age 3600
    python scripts/cleanup_stale_nodes.py --sid <case-uuid>
    python scripts/cleanup_stale_nodes.py --dry-run
"""
from __future__ import annotations

import argparse
import sys
import time

from dotenv import load_dotenv


DEFAULT_MAX_AGE_SECONDS = 86400  # 1 day


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Remove stale uncommitted nodes from the graph database."
    )
    parser.add_argument(
        "--max-age",
        type=int,
        default=DEFAULT_MAX_AGE_SECONDS,
        help=f"Maximum age in seconds before a node is considered stale (default: {DEFAULT_MAX_AGE_SECONDS})",
    )
    parser.add_argument(
        "--sid",
        type=str,
        default=None,
        help="Scope to a specific Case ID. If omitted, cleans all scopes.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without actually deleting.",
    )
    args = parser.parse_args()

    from dialectical_framework.settings import Settings

    settings = Settings.from_env()

    if settings.graph_db_vendor == "neo4j":
        from gqlalchemy import Neo4j
        graph_db = Neo4j(
            host=settings.graph_db_host,
            port=settings.graph_db_port,
            username=settings.graph_db_username or "",
            password=settings.graph_db_password or "",
            encrypted=settings.graph_db_encrypted,
        )
    else:
        from gqlalchemy import Memgraph
        graph_db = Memgraph(
            host=settings.graph_db_host,
            port=settings.graph_db_port,
        )

    cutoff = time.time() - args.max_age

    sid_filter = "AND n.sid = $sid" if args.sid else ""
    params: dict = {"cutoff": cutoff}
    if args.sid:
        params["sid"] = args.sid

    count_query = f"""
    MATCH (n)
    WHERE n.hash IS NULL
    AND n.saved_at IS NOT NULL
    AND n.saved_at < $cutoff
    {sid_filter}
    RETURN labels(n) AS labels, count(n) AS cnt
    """

    results = list(graph_db.execute_and_fetch(count_query, params))

    if not results or all(r["cnt"] == 0 for r in results):
        print("No stale nodes found.")
        return 0

    total = 0
    print(f"Stale nodes (saved_at < {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(cutoff))}):")
    for row in results:
        label = row["labels"][0] if row["labels"] else "Unknown"
        count = row["cnt"]
        total += count
        print(f"  {label}: {count}")
    print(f"  Total: {total}")

    if args.dry_run:
        print("\nDry run — no nodes deleted.")
        return 0

    delete_query = f"""
    MATCH (n)
    WHERE n.hash IS NULL
    AND n.saved_at IS NOT NULL
    AND n.saved_at < $cutoff
    {sid_filter}
    DETACH DELETE n
    """

    graph_db.execute(delete_query, params)
    print(f"\nDeleted {total} stale nodes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
