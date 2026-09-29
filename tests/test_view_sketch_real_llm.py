"""
The Consultant's view turn against a REAL model — the first time it runs
outside the mock brain.

What is checked: a short real consultation, then `exploration_view()` with no
focus (render what is established) and with a focus that requires BUILDING (a
full perspective for the thesis it named). Asserts are structural — a real
model's words are read by hand from the printed JSON, which is the point of
the run — plus the two contracts the mock cannot exercise: the flat DTO fills
without a ParseError on the json-mode thinking path, and the history record
is words, not a repr.
"""

from __future__ import annotations

import json
import time

import pytest

from dialectical_framework.agents.advisor.migration import message_text
from dialectical_framework.agents.apps import COUNSELOR_PERSONA
from dialectical_framework.agents.consultant.consultant import Consultant
from dialectical_framework.graph.views import ExplorationView


@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_a_real_consultation_draws_its_own_structure():
    head = Consultant(app_preamble=COUNSELOR_PERSONA)

    t0 = time.perf_counter()
    r1 = await head.chat(
        "I can't decide whether to keep our Berlin office or consolidate everything "
        "in Zurich. Twelve people work in Berlin and the German clients like having "
        "us close, but running two sites is slowing every decision down."
    )
    r2 = await head.chat("What's the real tension you see here?")
    chat_s = time.perf_counter() - t0
    print(f"\n--- reply 1 ({len(r1)} chars) ---\n{r1}\n--- reply 2 ---\n{r2}\n(chat {chat_s:.1f}s)")

    t1 = time.perf_counter()
    established = await head.exploration_view()
    s1 = time.perf_counter() - t1
    print(f"\n=== exploration_view() — established ({s1:.1f}s) ===")
    print(json.dumps(established.to_dict(), indent=1))
    print("--- history record ---\n" + message_text(head.messages[-1]))

    t2 = time.perf_counter()
    built = await head.exploration_view(
        focus="a full perspective for the thesis you named — all four aspects and both axes"
    )
    s2 = time.perf_counter() - t2
    print(f"\n=== exploration_view(focus=build) ({s2:.1f}s) ===")
    print(json.dumps(built.to_dict(), indent=1))
    print("--- history record ---\n" + message_text(head.messages[-1]))

    r3 = await head.chat("Which of those corners am I most at risk of drifting into?")
    print(f"\n--- reply 3 (asks about a drawn corner) ---\n{r3}")

    for view in (established, built):
        assert isinstance(view, ExplorationView)
        assert view.nexus_hash is None
        assert view.without_terminology() == view
    assert built.perspectives, "a build-focused ask must draw at least one perspective"
    first = built.perspectives[0]
    assert first.t is not None and first.a is not None
    assert first.complete, f"asked for a full perspective, got poles {sorted(first.poles)}"
    assert first.intent and first.intent.startswith("Reading along: ")
    assert "ViewSketchPerspectiveDto(" not in message_text(head.messages[-3]), (
        "the history holds words, not a repr"
    )
