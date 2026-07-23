#!/usr/bin/env python3
"""Delete degenerate Cycles (and their exclusively-owned Wheels) from the graph.

A degenerate Cycle is one whose ``perspective_hashes`` list contains duplicate
perspective hashes: a cycle claiming to be "layer N" that actually references
fewer than N *distinct* perspectives. These corrupt multi-PP wheel rendering
(the wheel shows only one perspective; dropdown labels repeat an index).

Root cause is fixed in code (Cycle.set_perspectives rejects duplicates;
PerspectiveCombination and CreateNexus dedup their inputs). This script removes
the already-persisted debris so it stops rendering broken.

Detection predicate (Python-side — Memgraph cannot dedup a list in Cypher):
    len(set(perspective_hashes)) != len(perspective_hashes)

Deletion scope, per degenerate Cycle:
    - the Cycle itself
    - each Wheel whose EVERY parent Cycle is degenerate (wheels can be shared
      across sibling cycles, so a wheel with any healthy parent is preserved)
    - for each such Wheel: its edge Transitions, its Transformations (and their
      Ac/Re/Ac±/Re± Transitions), and its Synthesis nodes

Safety:
    - --sid is REQUIRED (never operate graph-wide)
    - dry-run by default; pass --execute to actually delete
    - only committed cycles (hash IS NOT NULL) are considered

Usage:
    python scripts/cleanup_degenerate_cycles.py --sid <case-uuid>            # dry run
    python scripts/cleanup_degenerate_cycles.py --sid <case-uuid> --execute  # delete
"""

from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv


def _connect():
    from dialectical_framework.settings import Settings

    settings = Settings.from_env()

    if settings.graph_db_vendor == "neo4j":
        from gqlalchemy import Neo4j

        return Neo4j(
            host=settings.graph_db_host,
            port=settings.graph_db_port,
            username=settings.graph_db_username or "",
            password=settings.graph_db_password or "",
            encrypted=settings.graph_db_encrypted,
        )

    from gqlalchemy import Memgraph

    return Memgraph(host=settings.graph_db_host, port=settings.graph_db_port)


def _is_degenerate(perspective_hashes) -> bool:
    """A cycle is degenerate if its perspective_hashes list has any repeat."""
    if not perspective_hashes:
        return False
    return len(set(perspective_hashes)) != len(perspective_hashes)


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Remove degenerate Cycles (duplicate perspective_hashes) from the graph."
    )
    parser.add_argument(
        "--sid",
        type=str,
        required=True,
        help="Case ID (sid) to scope the cleanup to. REQUIRED.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete. Without this flag the script only reports (dry run).",
    )
    args = parser.parse_args()

    db = _connect()
    sid = args.sid

    # 1. Load every committed cycle's hash + perspective_hashes for this sid.
    cycles = list(
        db.execute_and_fetch(
            "MATCH (c:Cycle {sid: $sid}) WHERE c.hash IS NOT NULL "
            "RETURN c.hash AS hash, c.perspective_hashes AS ph",
            {"sid": sid},
        )
    )

    degenerate_hashes = {r["hash"] for r in cycles if _is_degenerate(r["ph"])}

    print(f"Scope sid={sid}")
    print(f"  Committed cycles:  {len(cycles)}")
    print(f"  Degenerate cycles: {len(degenerate_hashes)}")

    if not degenerate_hashes:
        print("\nNothing to clean up.")
        return 0

    for r in cycles:
        if r["hash"] in degenerate_hashes:
            ph = r["ph"] or []
            short = [h[:7] for h in ph]
            print(
                f"    - {r['hash'][:7]}  layer={len(ph)} distinct={len(set(ph))}  {short}"
            )

    # 2. Find wheels whose EVERY parent cycle is degenerate (safe to delete).
    #    A wheel shared with a healthy cycle must be preserved.
    wheel_rows = list(
        db.execute_and_fetch(
            """
            MATCH (c:Cycle {sid: $sid})-[:HAS_WHEEL]->(w:Wheel)
            WHERE c.hash IS NOT NULL AND w.hash IS NOT NULL
            RETURN w.hash AS wheel_hash, collect(c.hash) AS cycle_hashes
            """,
            {"sid": sid},
        )
    )

    deletable_wheels: list[str] = []
    preserved_wheels: list[str] = []
    for row in wheel_rows:
        parents = set(row["cycle_hashes"])
        if parents & degenerate_hashes:
            if parents <= degenerate_hashes:
                deletable_wheels.append(row["wheel_hash"])
            else:
                preserved_wheels.append(row["wheel_hash"])

    print(f"\n  Wheels to delete (all parents degenerate): {len(deletable_wheels)}")
    if preserved_wheels:
        print(
            f"  Wheels PRESERVED (shared with healthy cycle):  {len(preserved_wheels)}"
        )
        for wh in preserved_wheels:
            print(f"    - {wh[:7]} (still referenced by a non-degenerate cycle)")

    # 3. Count the wheel-subordinate nodes that will go with the wheels.
    #    edge Transitions (BELONGS_TO_CYCLE), Transformations (ACTION_REFLECTION
    #    to edges) + their own Transitions, and Synthesis (SYNTHESIS_OF).
    subordinate_counts = {
        "edge_transitions": 0,
        "transformations": 0,
        "transformation_transitions": 0,
        "synthesis": 0,
    }
    if deletable_wheels:
        counts = list(
            db.execute_and_fetch(
                """
                MATCH (w:Wheel) WHERE w.hash IN $wheels
                OPTIONAL MATCH (et:Transition)-[:BELONGS_TO_CYCLE]->(w)
                OPTIONAL MATCH (tf:Transformation)-[:ACTION_REFLECTION]->(:Transition)-[:BELONGS_TO_CYCLE]->(w)
                OPTIONAL MATCH (tf)-[:AC|RE|AC_PLUS|AC_MINUS|RE_PLUS|RE_MINUS]->(tt:Transition)
                OPTIONAL MATCH (s:Synthesis)-[:SYNTHESIS_OF]->(w)
                RETURN count(DISTINCT et) AS edges,
                       count(DISTINCT tf) AS transformations,
                       count(DISTINCT tt) AS transformation_transitions,
                       count(DISTINCT s) AS synthesis
                """,
                {"wheels": deletable_wheels},
            )
        )
        if counts:
            row = counts[0]
            subordinate_counts = {
                "edge_transitions": row["edges"],
                "transformations": row["transformations"],
                "transformation_transitions": row["transformation_transitions"],
                "synthesis": row["synthesis"],
            }

    print("\n  Subordinate nodes to delete with those wheels:")
    for k, v in subordinate_counts.items():
        print(f"    {k}: {v}")

    if not args.execute:
        print("\nDry run — nothing deleted. Re-run with --execute to delete.")
        return 0

    # 4. Delete, deepest first, to avoid dangling references.
    params_w = {"wheels": deletable_wheels}

    if deletable_wheels:
        # Transformation transitions (Ac/Re/Ac±/Re±) owned by transformations
        # whose edge belongs to a deletable wheel.
        db.execute(
            """
            MATCH (tf:Transformation)-[:ACTION_REFLECTION]->(:Transition)-[:BELONGS_TO_CYCLE]->(w:Wheel)
            WHERE w.hash IN $wheels
            MATCH (tf)-[:AC|RE|AC_PLUS|AC_MINUS|RE_PLUS|RE_MINUS]->(tt:Transition)
            DETACH DELETE tt
            """,
            params_w,
        )
        # Transformations themselves
        db.execute(
            """
            MATCH (tf:Transformation)-[:ACTION_REFLECTION]->(:Transition)-[:BELONGS_TO_CYCLE]->(w:Wheel)
            WHERE w.hash IN $wheels
            DETACH DELETE tf
            """,
            params_w,
        )
        # Synthesis nodes
        db.execute(
            """
            MATCH (s:Synthesis)-[:SYNTHESIS_OF]->(w:Wheel)
            WHERE w.hash IN $wheels
            DETACH DELETE s
            """,
            params_w,
        )
        # Edge transitions
        db.execute(
            """
            MATCH (et:Transition)-[:BELONGS_TO_CYCLE]->(w:Wheel)
            WHERE w.hash IN $wheels
            DETACH DELETE et
            """,
            params_w,
        )
        # Wheels
        db.execute(
            "MATCH (w:Wheel) WHERE w.hash IN $wheels DETACH DELETE w",
            params_w,
        )

    # Finally the degenerate cycles.
    db.execute(
        "MATCH (c:Cycle) WHERE c.hash IN $cycles DETACH DELETE c",
        {"cycles": list(degenerate_hashes)},
    )

    print(
        f"\nDeleted {len(degenerate_hashes)} degenerate cycles and "
        f"{len(deletable_wheels)} wheels (plus their transitions, transformations, "
        f"and synthesis)."
    )
    print("Re-run BuildWheels for this sid to regenerate clean structures.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
