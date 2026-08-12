"""Probe: does the A2 prompt the BENCH builds actually carry the explore doc?"""

from __future__ import annotations

import pytest

from dialectical_framework.agents.advisor.advisor import Advisor


@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


def test_probe_explore_doc_renders():
    a = Advisor(app_preamble="You are a thoughtful advisor.", principal="agent:probe")
    prompt = a._build_system_prompt()
    print("\n=== prompt chars:", len(prompt))
    for needle in (
        "`explore`",
        "ONE mapped tension is already enough",
        "A decision closes on pathways, not on tensions alone",
        "Grounded in:",
        "record_decision",
    ):
        print(f"  {needle!r:58} -> {needle in prompt}")

    # Where does explore sit relative to the tool list and the decision section?
    print("\n  index of explore doc:", prompt.find("- `explore`"))
    print("  index of pathways rule:", prompt.find("A decision closes on pathways"))
    print("  index of Decision Readiness hdr:", prompt.find("Decision Readiness"))
    print("  total length:", len(prompt))
