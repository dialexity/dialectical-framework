"""What does the source listing cost when the sources are big?

`_dump_inputs` renders nothing but short hashes, yet it gets there through
`InputRepository.get_all()`, which is `RETURN i` — the whole node, `content`
included. The context dump fires on ~86% of turns, so if that transfer is
expensive it is expensive on almost every turn, and it grows with the size of
whatever the person pasted rather than with anything the model reads.

The comparison is `get_all()` (full nodes) against the projection the renderer
would actually need (hashes only), over the same seeded scope. No LLM.

Run: poetry run pytest tests/probe_source_listing_cost.py -s -p no:randomly
Not collected by the default suite (`probe_*.py`), and asserts nothing — the
output IS the result.
"""

from __future__ import annotations

import statistics
import time

import pytest

from dialectical_framework.concerns.dialectical_context import DialecticalContext
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.input import Input
from dialectical_framework.graph.repositories.input_repository import \
    InputRepository
from dialectical_framework.graph.scope_context import scope

REPS = 7


def _seed(case: Case, count: int, body_chars: int) -> None:
    for i in range(count):
        node = Input(content=f"source {i} " + ("lorem ipsum " * (body_chars // 12)))
        node.commit()
        case.inputs.connect(node)


def _hashes_only(sid: str, graph_db) -> list[str]:
    """The projection `_dump_inputs` would use — same filter, no content."""
    query = """
    MATCH (i:Input)
    WHERE i.sid = $sid AND i.hash IS NOT NULL
    RETURN i.hash AS hash
    ORDER BY hash
    """
    return [r["hash"] for r in graph_db.execute_and_fetch(query, {"sid": sid})]


def _time(fn) -> float:
    samples = []
    for _ in range(REPS):
        started = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - started)
    return statistics.median(samples)


@pytest.mark.parametrize(
    "count,body_chars",
    [(3, 200), (3, 400_000), (10, 400_000)],
)
def test_source_listing_cost(count: int, body_chars: int, di_container):
    case = Case()
    case.commit()
    graph_db = di_container.graph_db()

    with scope(case.sid):
        _seed(case, count, body_chars)
        repo = InputRepository()

        full = _time(lambda: repo.get_all())
        projected = _time(lambda: _hashes_only(case.sid, graph_db))
        analyzed = _time(lambda: repo.analyzed_hashes())
        dump = _time(lambda: DialecticalContext._dump_inputs())

    total = count * body_chars
    print(
        f"\n{count} inputs x {body_chars:,} chars ({total:,} total)"
        f"\n  get_all() full nodes : {full * 1000:8.1f} ms"
        f"\n  hashes-only projection: {projected * 1000:8.1f} ms"
        f"\n  analyzed_hashes()     : {analyzed * 1000:8.1f} ms"
        f"\n  _dump_inputs() whole  : {dump * 1000:8.1f} ms"
        f"\n  transfer saved        : {(full - projected) * 1000:8.1f} ms"
    )
