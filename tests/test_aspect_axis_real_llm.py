"""Real-LLM behavioral check for the axis-of-opposition fix (closed issue #25).

Drives AspectGeneration on the exact Tree/Mother pair from the issue plus a set
of contrasting T/A pairs — some genuine dialectical oppositions, some arbitrary
non-oppositions — and prints the `axis` each diagonal pair reports, so we can
see whether the model now (a) produces a coherent axis for real oppositions and
(b) signals "no shared axis" for arbitrary pairs instead of fabricating.

Run: poetry run pytest tests/test_aspect_axis_real_llm.py -s --real-llm
(Skipped in the default suite — needs a real provider.)
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.real_llm, pytest.mark.llm]

from conftest import traced

from dialectical_framework.concerns.aspect_generation import (AspectGeneration,
                                                              TetradDto)
from dialectical_framework.concerns.statement_classification import \
    StatementClassification
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.perspective import Perspective
from dialectical_framework.graph.nodes.polarity import Polarity
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.relationships.polarity_relationship import \
    HasPolarityRelationship
from dialectical_framework.graph.scope_context import scope


# (thesis, antithesis, is_genuine_opposition)
PAIRS = [
    ("Tree", "Mother", False),          # the issue's own arbitrary pair
    ("Coffee", "Tuesday", False),       # obviously unrelated control
    ("Freedom", "Security", True),      # genuine dialectical tension
    ("Individual", "Collective", True), # genuine dialectical tension
]


async def _generate_tetrad_capturing_axis(t_text: str, a_text: str) -> TetradDto:
    """Run the real full-tetrad generation and return the raw DTO (with axes).

    Both poles are classified through the real `StatementClassification`, as
    `anchor`'s `IntroducePolarity._classify_statement` does. This is not optional
    fixture polish: `AspectGeneration._tetrad_prompt` interpolates
    `lookup_aspect_apex()` for all four positions, and that lookup raises on a
    meaning that does not parse to a known taxonomy branch. This test previously
    passed `meaning=t_text.lower()` and so raised `ValueError: Parent meaning
    'tree' has no known taxonomy branch` in the prompt builder, before reaching the
    provider — it failed on every pair and, being `real_llm`-marked, was skipped in
    the default suite where that would have been noticed.
    """
    pp = Perspective()
    pp.save()

    t_class = await StatementClassification().resolve(statement=t_text)
    a_class = await StatementClassification().resolve(statement=a_text)

    t = Statement(text=t_text, meaning=t_class.meaning)
    t.commit()
    a = Statement(text=a_text, meaning=a_class.meaning)
    a.commit()

    polarity = Polarity()
    polarity.set_t(t, heuristic_similarity=1.0)
    polarity.set_a(a, heuristic_similarity=0.8)
    polarity.commit()
    pp.polarity.connect(polarity, relationship=HasPolarityRelationship())

    gen = AspectGeneration()

    # Wrap submit to capture the raw TetradDto (resolve() discards the axis).
    captured: list[TetradDto] = []
    original_submit = gen._conversation.submit

    async def _capturing_submit(**kwargs):
        result = await original_submit(**kwargs)
        if isinstance(result, TetradDto):
            captured.append(result)
        return result

    gen._conversation.submit = _capturing_submit  # type: ignore[method-assign]

    await gen.resolve(perspective=pp, text="")
    assert captured, "expected a TetradDto from the full-tetrad path"
    return captured[0]


@pytest.mark.asyncio
@traced
async def test_axis_signals_opposition_strength():
    """Print each pair's axes; assert genuine oppositions name a coherent axis."""
    case_node = Case()
    case_node.commit()

    print("\n\n=== Axis-of-opposition behavioral check ===")
    with scope(case_node.sid):
        for t_text, a_text, genuine in PAIRS:
            dto = await _generate_tetrad_capturing_axis(t_text, a_text)

            label = "GENUINE" if genuine else "ARBITRARY"
            print(f"\n[{label}] T = {t_text!r}, A = {a_text!r}")
            print(f"  Pair T+/A-  axis: {dto.t_plus_vs_a_minus_axis!r}")
            print(f"    T+ = {dto.t_plus.statement!r}")
            print(f"    A- = {dto.a_minus.statement!r}")
            print(f"  Pair A+/T-  axis: {dto.a_plus_vs_t_minus_axis!r}")
            print(f"    A+ = {dto.a_plus.statement!r}")
            print(f"    T- = {dto.t_minus.statement!r}")

            # A genuine opposition must produce a non-empty axis for both pairs.
            if genuine:
                assert dto.t_plus_vs_a_minus_axis.strip(), f"{t_text}/{a_text}: empty T+/A- axis"
                assert dto.a_plus_vs_t_minus_axis.strip(), f"{t_text}/{a_text}: empty A+/T- axis"

    print("\n=== end ===\n")
