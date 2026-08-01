"""Real-LLM spot-check of DV scoring against the paper's reference values.

The paper's own evaluations [P1 S1.7, Tables S1.7-1/-2] give reference DV
orderings we can test against (ranking, not exact values — different model):

- Balanced Love/Hate control statements: DV ~0.95-0.99 (high)
- Orwellian tetrad (Official Truth / Heresy / Propaganda / Free Thought):
  DV ~0.0-0.05 (near zero) — even when CC scored as high as 0.85 on some
  models. This is the case that separates DV from CC.

If DV comes back HIGH on the Orwellian-style tetrad, the same-call scoring
fork (see CoherenceEvaluationDto docstring) is anchoring DV on CC — split DV
into its own call.

Run: poetry run pytest tests/test_dialectical_validity_real_llm.py -s --real-llm
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.real_llm, pytest.mark.llm]

from conftest import traced

from dialectical_framework.concerns.control_statements_check import \
    ControlStatementsCheck
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.scope_context import scope
from test_analyst_validation import _create_test_perspective


@pytest.mark.asyncio
@traced
async def test_dv_separates_natural_from_coerced_tetrads():
    """DV must rank the balanced Love/Hate tetrad above the Orwellian one."""
    case_node = Case()
    case_node.commit()

    with scope(case_node.sid):
        # Paper's balanced exemplar [P0 Table 7 / P1 S1.7-1]
        balanced = _create_test_perspective(
            t_statement="Love",
            a_statement="Hate",
            t_plus_statement="Bonding",
            t_minus_statement="Enmeshment",
            a_plus_statement="Autonomy",
            a_minus_statement="Alienation",
        )
        # Paper's coerced exemplar [P1 S1.7-2]: coherent-sounding but
        # dialectically distorted (outcomes enforced by coercion/ideology)
        orwellian = _create_test_perspective(
            t_statement="Official Truth",
            a_statement="Heresy",
            t_plus_statement="Propaganda",
            t_minus_statement="Dogma",
            a_plus_statement="Free Thought",
            a_minus_statement="Chaos",
        )

        checker_b = ControlStatementsCheck()
        result_b = await checker_b.resolve(perspective=balanced)
        checker_o = ControlStatementsCheck()
        result_o = await checker_o.resolve(perspective=orwellian)

        dv_b = result_b.dv_estimation.value
        dv_o = result_o.dv_estimation.value
        cc_b = result_b.estimation.value
        cc_o = result_o.estimation.value

        print(f"\nBalanced (Love/Hate):      CC={cc_b:.2f}  DV={dv_b:.2f}")
        print(f"Orwellian (Official Truth): CC={cc_o:.2f}  DV={dv_o:.2f}")

        # The paper's core claim: DV separates these (0.95+ vs ~0.0).
        # Ranking assertion only — exact values are model-calibrated.
        assert dv_b > dv_o, (
            f"DV failed to rank balanced ({dv_b:.2f}) above Orwellian "
            f"({dv_o:.2f}) — if CC and DV track each other here, the "
            f"same-call fork is anchoring; split DV into its own call"
        )
        # The gap should be substantial, not marginal (paper: ~0.9 apart)
        assert dv_b - dv_o > 0.3, (
            f"DV gap too small ({dv_b:.2f} vs {dv_o:.2f}); paper separates "
            f"these by ~0.9 — check the same-call anchoring fork"
        )
