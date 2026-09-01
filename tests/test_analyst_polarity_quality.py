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

    def test_status_distinguishes_deferred_from_set_aside(self):
        """`expanded: False` conflates two opposite situations, and only one of
        them is work still owed.

        `ccc` at 0.75 cleared the gate and lost to the budget — a follow-up call
        would develop it. `bbb` at 0.4 was judged a weak opposition and there is
        nothing to come back for. The boolean above cannot tell them apart, so
        the agent reading only `expanded` would either chase both or neither.
        """
        from dialectical_framework.agents.analyst.analyst import AnalysisPipeline

        quality = AnalysisPipeline._build_polarity_quality(
            self._data(), hashes_to_expand=["aaa"]
        )

        by_hash = {q["polarity_hash"]: q for q in quality}
        assert by_hash["aaa"]["status"] == "expanded"
        assert by_hash["ccc"]["status"] == "deferred"
        assert by_hash["bbb"]["status"] == "set_aside"

    def test_unscored_tension_is_set_aside_not_deferred(self):
        """A `None` HS is an absent judgement, not a passing one.

        `hs is not None and hs >= HS_THRESHOLD` reads as belt-and-braces until you
        drop the first clause, at which point `None >= 0.7` raises.

        What that guard does NOT buy is safety for a real run, and the first
        version of this docstring claimed it did. `_rank_polarities` is handed the
        same list one line earlier (`analyst.py:361` before `:375`) and has no
        such guard, so a `polarity_data` carrying an explicit `None` dies there
        first and never reaches this function. The guard makes this function
        correct in ISOLATION — which is what the test asserts, and all it asserts.
        """
        from dialectical_framework.agents.analyst.analyst import AnalysisPipeline

        data = [
            {"polarity_hash": "aaa", "thesis_text": "T1", "antithesis_text": "A1", "heuristic_similarity": None},
        ]
        quality = AnalysisPipeline._build_polarity_quality(data, hashes_to_expand=[])

        assert quality[0]["status"] == "set_aside"

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


class TestRankPolaritiesGate:
    """The gate itself, which until now had no test at all.

    `_build_polarity_quality` above only REPORTS the gate's outcome; it is handed
    `hashes_to_expand` already decided. `_rank_polarities` is what decides, and
    it is the most consequential arithmetic on the `anchor` thesis-only branch:
    it selects which tensions get a full tetrad and therefore what the person is
    shown. The existing end-to-end test (`test_anchor_fanout_expansion.py`)
    hardcodes `heuristic_similarity=0.85` on all five antitheses, so the gate
    passes trivially there and neither boundary is ever crossed.

    Pure logic over plain dicts — no LLM, no graph — so the boundaries can be
    pinned exactly rather than sampled.

    One asymmetry deliberately NOT asserted here: `_rank_polarities` sorts on
    `p.get("heuristic_similarity", 0)`, whose default applies only when the key
    is ABSENT, so an entry carrying an explicit `None` raises TypeError where
    `_build_polarity_quality` handles it. Unreachable as the code stands — every
    `heuristic_similarity` on the result models feeding this is a non-Optional
    `float` — so a test asserting the raise would pin a crash as if it were
    intended. Recorded rather than locked in.
    """

    @staticmethod
    def _pipeline():
        from dialectical_framework.agents.analyst.analyst import AnalysisPipeline

        # Constructing the pipeline touches no DB and issues no call; only
        # `resolve()` does. `_rank_polarities` needs an instance solely because
        # it is a method — it reads nothing off `self`.
        return AnalysisPipeline(thesis_hashes=["h1"])

    @staticmethod
    def _entry(name: str, hs: float, **extra) -> dict:
        return {"polarity_hash": name, "heuristic_similarity": hs, **extra}

    def test_threshold_is_inclusive(self):
        """`>= HS_THRESHOLD`, so a tension landing exactly on 0.7 is developed.

        Pinned because the difference between `>` and `>=` here is invisible in
        every existing test and decides the fate of a genuine boundary case.
        """
        from dialectical_framework.agents.analyst.analyst import HS_THRESHOLD

        kept = self._pipeline()._rank_polarities(
            [self._entry("on", HS_THRESHOLD), self._entry("under", HS_THRESHOLD - 0.01)]
        )

        assert [p["polarity_hash"] for p in kept] == ["on"]

    def test_sub_threshold_dropped_when_anything_clears(self):
        kept = self._pipeline()._rank_polarities(
            [self._entry("strong", 0.9), self._entry("weak", 0.2)]
        )

        assert [p["polarity_hash"] for p in kept] == ["strong"]

    def test_soft_fallback_keeps_the_top_few_when_nothing_clears(self):
        """The branch no test has ever exercised, and the surprising one.

        A run where every opposition is weak does NOT come back empty — the
        threshold is abandoned and the top few are expanded anyway. That is a
        deliberate refusal to hand the person nothing, but it means a reported
        perspective is NOT evidence that its tension cleared 0.7. Anyone reading
        HS as a quality guarantee downstream is reading it wrong, and this test
        is where that is written down.
        """
        kept = self._pipeline()._rank_polarities(
            [self._entry("best", 0.4), self._entry("worse", 0.3)]
        )

        assert [p["polarity_hash"] for p in kept] == ["best", "worse"]

    def test_fallback_ranks_hs_descending(self):
        kept = self._pipeline()._rank_polarities(
            [self._entry("mid", 0.3), self._entry("top", 0.5), self._entry("low", 0.1)]
        )

        assert [p["heuristic_similarity"] for p in kept] == [0.5, 0.3, 0.1]

    def test_truncates_to_the_expansion_budget(self):
        """Above the threshold, the budget still bites — and it takes the best."""
        from dialectical_framework.agents.analyst.analyst import \
            MAX_POLARITIES_TO_EXPAND

        data = [self._entry(f"p{i}", 0.70 + i / 100) for i in range(MAX_POLARITIES_TO_EXPAND + 2)]
        kept = self._pipeline()._rank_polarities(data)

        assert len(kept) == MAX_POLARITIES_TO_EXPAND
        # Descending, so the two dropped are the two weakest, not the last two
        # the extractor happened to emit.
        assert [p["polarity_hash"] for p in kept] == [
            f"p{i}" for i in range(len(data) - 1, len(data) - 1 - MAX_POLARITIES_TO_EXPAND, -1)
        ]

    def test_fallback_respects_the_same_budget(self):
        """The soft fallback is a floor on quality, not on quantity."""
        from dialectical_framework.agents.analyst.analyst import \
            MAX_POLARITIES_TO_EXPAND

        data = [self._entry(f"p{i}", 0.1 + i / 100) for i in range(MAX_POLARITIES_TO_EXPAND + 3)]
        kept = self._pipeline()._rank_polarities(data)

        assert len(kept) == MAX_POLARITIES_TO_EXPAND

    def test_deduped_and_hashless_never_expand(self):
        """Excluded BEFORE the threshold, so they cannot occupy the budget.

        A deduped tension is already represented by the one it collapsed into;
        expanding it would spend a slot generating a second tetrad for the same
        opposition. Note this also means a high-HS duplicate cannot rescue a run
        into the `above_threshold` branch.
        """
        kept = self._pipeline()._rank_polarities(
            [
                self._entry("dupe", 0.95, deduped=True),
                {"polarity_hash": None, "heuristic_similarity": 0.95},
                self._entry("real", 0.4),
            ]
        )

        assert [p["polarity_hash"] for p in kept] == ["real"]

    def test_missing_hs_key_sorts_as_zero(self):
        """An entry that never carried the field ranks last but is not dropped.

        This is the `.get(..., 0)` default, and it is reachable in a way an
        explicit `None` is not: a caller building the dict without the key at
        all. It must not crash the run, and it must not outrank a scored one.
        """
        kept = self._pipeline()._rank_polarities(
            [{"polarity_hash": "bare"}, self._entry("scored", 0.3)]
        )

        assert [p["polarity_hash"] for p in kept] == ["scored", "bare"]

    def test_empty_input_expands_nothing(self):
        assert self._pipeline()._rank_polarities([]) == []


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
