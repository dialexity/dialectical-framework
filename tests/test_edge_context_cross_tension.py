"""`build_edge_context` warns when an edge crosses two tensions, and only then.

At N >= 2 the relative labels ("A" = the target) were read as T's own
antithesis: a third of staged Ac+ turned T's trap into T's OWN tension's
strength (`tests/e2e/probe_n2_one_shot_edge.py`, 2026-10-06). The note says the
two segments are different tensions; a one-tension edge, where the target IS
T's other side, says nothing. DB-free: segments are stand-ins with the same
accessor shape (`.t.get()` -> (statement, rel), `.opposite`).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from dialectical_framework.utils.edge_context import (CROSS_TENSION_NOTE,
                                                      _crosses_tensions,
                                                      build_edge_context)


@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


def _stmt(text: str):
    return SimpleNamespace(prompt_text=text, hash=f"h-{text}")


def _rel(stmt):
    return SimpleNamespace(get=lambda: (stmt, None))


def _segment(t: str, plus: str, minus: str, opposite=None):
    seg = SimpleNamespace(t=_rel(_stmt(t)), t_plus=_rel(_stmt(plus)), t_minus=_rel(_stmt(minus)))
    seg.opposite = opposite
    return seg


def _tension(t: str, a: str):
    """Two segments that are each other's opposite: one tension."""
    t_seg = _segment(t, f"{t}+", f"{t}-")
    a_seg = _segment(a, f"{a}+", f"{a}-", opposite=t_seg)
    t_seg.opposite = a_seg
    return t_seg, a_seg


def test_one_tension_edge_says_nothing():
    t1, a1 = _tension("Quit the job", "Keep the job")
    assert not _crosses_tensions(t1, a1)
    assert CROSS_TENSION_NOTE not in build_edge_context(t1, a1)


def test_an_edge_across_two_tensions_carries_the_note():
    t1, _a1 = _tension("Quit the job", "Keep the job")
    _t2, a2 = _tension("Build alone", "Bring in partners")
    assert _crosses_tensions(t1, a2)
    context = build_edge_context(t1, a2)
    assert context.endswith(CROSS_TENSION_NOTE)
    assert "TWO DIFFERENT tensions" in CROSS_TENSION_NOTE


def test_a_missing_statement_reads_as_not_crossing():
    t1, _a1 = _tension("Quit the job", "Keep the job")
    empty = SimpleNamespace(t=SimpleNamespace(get=lambda: None), opposite=None)
    assert not _crosses_tensions(t1, empty)
