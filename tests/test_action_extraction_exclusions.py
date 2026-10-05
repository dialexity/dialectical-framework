"""`ActionExtraction._build_exclusion_list` names PATHWAYS, not poles.

Found by the 2026-10-05 review: the list collected the Ac+ transition's target
(the segment's A+ pole), so the prompt's "already covered" section listed
poles and the post-filter on `candidate.statement` could never match. DB-free.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from dialectical_framework.concerns.action_extraction import ActionExtraction


@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


def _transformation(instruction: str | None, summary: str | None = None, target_text: str = "A+ pole text"):
    target = SimpleNamespace(prompt_text=target_text, text=target_text)
    transition = SimpleNamespace(
        instruction=instruction, summary=summary,
        target=SimpleNamespace(get=lambda: (target, None)),
    )
    return SimpleNamespace(ac_plus=SimpleNamespace(get=lambda: (transition, None)))


class TestTheExclusionListNamesPathways:
    def test_the_ac_plus_instruction_is_what_is_excluded(self):
        got = ActionExtraction._build_exclusion_list(ActionExtraction(), [_transformation("Set a weekly venture hour")])
        assert got == ["Set a weekly venture hour"]
        assert "A+ pole text" not in got, "the target pole is not a pathway"

    def test_summary_stands_in_for_a_missing_instruction_and_blank_is_dropped(self):
        got = ActionExtraction._build_exclusion_list(
            ActionExtraction(), [_transformation(None, "Restructure hours into a sprint"), _transformation("  ", None)]
        )
        assert got == ["Restructure hours into a sprint"]

    def test_no_ac_plus_means_nothing_to_exclude(self):
        empty = SimpleNamespace(ac_plus=SimpleNamespace(get=lambda: None))
        assert ActionExtraction._build_exclusion_list(ActionExtraction(), [empty]) == []
