"""
Regression tests for surfacing the HS-based polarity gate to the Analyst.

`AnalysisPipeline._rank_polarities` silently drops tensions below HS_THRESHOLD
(and beyond the top few). These tests lock in that the gate outcome is now
*visible* — via `_build_polarity_quality` and a corresponding system-prompt
section — so the agent can explain which framings are strong and which were
set aside instead of dropping them silently.

Pure logic / string assertions — no LLM, no graph DB — so they run in the
default suite.
"""

from __future__ import annotations

import pytest


# DB-free: override the autouse graph fixtures (per CLAUDE.md DB-free convention).
@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


class TestBuildPolarityQuality:
    def _data(self) -> list[dict]:
        return [
            {"polarity_hash": "aaa", "thesis_text": "T1", "antithesis_text": "A1", "heuristic_similarity": 0.9},
            {"polarity_hash": "bbb", "thesis_text": "T2", "antithesis_text": "A2", "heuristic_similarity": 0.4},
            {"polarity_hash": "ccc", "thesis_text": "T3", "antithesis_text": "A3", "heuristic_similarity": 0.75},
        ]

    def test_flags_expanded_vs_set_aside(self):
        from dialectical_framework.agents.analyst.analyst import AnalysisPipeline

        quality = AnalysisPipeline._build_polarity_quality(
            self._data(), hashes_to_expand=["aaa", "ccc"]
        )

        by_hash = {q["polarity_hash"]: q for q in quality}
        assert by_hash["aaa"]["expanded"] is True
        assert by_hash["ccc"]["expanded"] is True
        assert by_hash["bbb"]["expanded"] is False, "Sub-threshold tension must be flagged set-aside, not dropped"

    def test_sorted_hs_descending(self):
        from dialectical_framework.agents.analyst.analyst import AnalysisPipeline

        quality = AnalysisPipeline._build_polarity_quality(
            self._data(), hashes_to_expand=["aaa", "ccc"]
        )

        hs_values = [q["hs"] for q in quality]
        assert hs_values == sorted(hs_values, reverse=True)

    def test_every_non_deduped_tension_surfaces(self):
        """The agent must see set-aside tensions too — not just the expanded ones."""
        from dialectical_framework.agents.analyst.analyst import AnalysisPipeline

        quality = AnalysisPipeline._build_polarity_quality(
            self._data(), hashes_to_expand=["aaa"]
        )

        assert len(quality) == 3, "All three tensions should surface regardless of gate"
        assert sum(1 for q in quality if not q["expanded"]) == 2

    def test_deduped_and_hashless_excluded(self):
        from dialectical_framework.agents.analyst.analyst import AnalysisPipeline

        data = self._data() + [
            {"polarity_hash": "ddd", "thesis_text": "T4", "antithesis_text": "A4", "heuristic_similarity": 0.8, "deduped": True},
            {"polarity_hash": None, "thesis_text": "T5", "antithesis_text": "A5", "heuristic_similarity": 0.8},
        ]
        quality = AnalysisPipeline._build_polarity_quality(data, hashes_to_expand=["aaa"])

        hashes = {q["polarity_hash"] for q in quality}
        assert "ddd" not in hashes, "Deduped tensions must not surface"
        assert None not in hashes, "Hashless entries must be skipped"

    def test_duplicate_hashes_collapsed(self):
        from dialectical_framework.agents.analyst.analyst import AnalysisPipeline

        data = self._data() + [
            {"polarity_hash": "aaa", "thesis_text": "T1", "antithesis_text": "A1", "heuristic_similarity": 0.9},
        ]
        quality = AnalysisPipeline._build_polarity_quality(data, hashes_to_expand=["aaa"])

        assert [q["polarity_hash"] for q in quality].count("aaa") == 1

    def test_none_hs_sorts_last_without_error(self):
        from dialectical_framework.agents.analyst.analyst import AnalysisPipeline

        data = [
            {"polarity_hash": "aaa", "thesis_text": "T1", "antithesis_text": "A1", "heuristic_similarity": None},
            {"polarity_hash": "bbb", "thesis_text": "T2", "antithesis_text": "A2", "heuristic_similarity": 0.6},
        ]
        quality = AnalysisPipeline._build_polarity_quality(data, hashes_to_expand=["bbb"])

        assert quality[0]["polarity_hash"] == "bbb"
        assert quality[-1]["polarity_hash"] == "aaa"


class TestAnalystPromptTeachesHS:
    def test_prompt_has_polarity_quality_section(self):
        from dialectical_framework.agents.analyst import system_prompts

        prompt = system_prompts.SYSTEM_PROMPT
        assert "Reading Polarity Quality" in prompt
        assert "HS" in prompt

    def test_prompt_directs_meaning_over_numbers(self):
        from dialectical_framework.agents.analyst import system_prompts

        prompt = system_prompts.SYSTEM_PROMPT.lower()
        # The gate must not be silent: the prompt tells the agent to acknowledge
        # set-aside tensions rather than drop them.
        assert "set aside" in prompt or "set-aside" in prompt
        assert "meaning" in prompt
