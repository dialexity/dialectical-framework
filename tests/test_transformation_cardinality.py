"""How many Transformations a wheel gets, and why the docs must say the same.

CLAUDE.md claimed "N-PP wheel = ... 2N Transformations. 1-PP = 2 edges/1 pair/2
Transformations" until 2026-08-13. It was counting EDGES. The real multiplier is
`INSIGHT_CATEGORIES`: `ActionExtraction` returns one Ac+ candidate per category
(Generative/Configurational/Corrective) and `ExploreTransformations` Phase 2
generates a tetrad — hence a Transformation node — per candidate. So 2N edges ×
3 categories = 6N, measured as 6 on a real provider for a 1-PP wheel
(`test_single_perspective_explore_real_llm.py`: 3 × `A → T`, 3 × `T → A`).

A stale cardinality is not a cosmetic doc bug. It is the number anyone reasoning
about explore latency, LLM spend, or "how many pathways can the model choose
between" reads first — and it was wrong by 3×. These tests bind the prose to
`INSIGHT_CATEGORIES` so adding a fourth category cannot silently triple the
stage while the docs keep saying 6N.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dialectical_framework.concerns.action_extraction import INSIGHT_CATEGORIES

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def cleanup_graph_db():
    """DB-free: override the autouse graph fixtures (per CLAUDE.md convention)."""
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


class TestTransformationsPerEdge:
    def test_one_ac_plus_candidate_per_insight_category(self):
        """The fan-out is the category dict — nothing else multiplies it.

        `ActionExtraction.resolve` gathers `_generate_candidate_for_category`
        once per `INSIGHT_CATEGORIES.items()`, and Phase 2 loops
        `for ac_plus in data.ac_candidates`. So this length IS the
        per-edge Transformation count.
        """
        assert set(INSIGHT_CATEGORIES) == {
            "Generative",
            "Configurational",
            "Corrective",
        }
        # The paper's own grouping of the 11-level Insight scale
        # (docs/theory/transformations-synthesis.md, status: implemented).
        assert len(INSIGHT_CATEGORIES) == 3

    def test_phase_two_spawns_one_tetrad_per_candidate(self):
        """Guard the loop shape without a graph: count what Phase 2 would spawn.

        Mirrors `_process_edge_pair`'s Phase-2 nesting — for each of the pair's
        two edges, one generation task per Ac+ candidate that finds an
        opposite-edge match. `_find_matching_category` falls back to
        `candidates[0]`, so a match always exists when the opposite edge has
        candidates: no candidate is dropped, and the count is exact.
        """
        from dialectical_framework.agents.explorer.skills.explore_transformations import \
            ExploreTransformations

        per_edge = len(INSIGHT_CATEGORIES)
        candidates = [
            _StubCandidate(label)
            for label in ("Leverage", "Composition", "Tuning")
        ]
        assert len(candidates) == per_edge

        spawned = 0
        for _edge, _opposite in ((0, 1), (1, 0)):
            for ac_plus in candidates:
                match = ExploreTransformations._find_matching_category(
                    candidates, ac_plus.insight_label
                )
                assert match is not None
                spawned += 1

        # 2 edges in the pair × 3 candidates = 6 Transformations for a 1-PP wheel
        assert spawned == 2 * per_edge == 6


class TestDocumentedCardinalityMatchesCode:
    """The prose is bound to `INSIGHT_CATEGORIES`, not hand-maintained.

    Both files carry the multiplier because both are read as authoritative:
    CLAUDE.md by anyone touching the exploration chain, the reasoning-layer map
    by anyone reviewing its prompts (and the map owes latency math besides).
    """

    @pytest.mark.parametrize(
        "doc",
        [
            "CLAUDE.md",
            ".claude/skills/df-review-reasoning-layer/reference/systemic-map.md",
        ],
    )
    def test_the_docs_state_the_multiplier_the_code_implements(self, doc):
        text = (REPO_ROOT / doc).read_text()
        n_per_wheel = 2 * len(INSIGHT_CATEGORIES)
        assert f"{n_per_wheel}N" in text, (
            f"{doc} must state Transformations = {n_per_wheel}N "
            f"(2 edges per PP × {len(INSIGHT_CATEGORIES)} insight categories). "
            "If INSIGHT_CATEGORIES changed, the docs and the cost math change with it."
        )

    def test_the_old_edge_counting_claim_is_gone(self):
        """`2N Transformations` was the bug — it must not come back."""
        text = (REPO_ROOT / "CLAUDE.md").read_text()
        assert "2N Transformations" not in text
        assert "1 pair/2 Transformations" not in text


class _StubCandidate:
    """Only what `_find_matching_category` reads."""

    def __init__(self, insight_label: str):
        self.insight_label = insight_label
