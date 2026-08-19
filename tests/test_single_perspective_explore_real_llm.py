"""Real-LLM check: exploring ONE perspective yields a usable pathway.

Why this matters, from the bench
--------------------------------
`claim2-weak-r4` flagged "5/6 live A2 runs never called explore" and three
prompt fixes aimed at that flag have failed. Reading the tool calls per run
explains why the flag resisted them:

    wobble_a rep1  ['anchor', 'record_decision', 'inspect_node']
    wobble_b rep1  ['anchor', 'record_decision']
    wobble_a rep2  ['anchor']
    wobble_b rep2  ['anchor', ..., 'explore', ...]   <- the 1 that explored
    wobble_a rep3  ['anchor', 'inspect_node', ...]
    wobble_b rep3  ['anchor']

Five of six called `anchor` exactly ONCE. So the model was not declining to
explore a map it had — it had one perspective, and the prompt's floor reads as
two ("Two mapped tensions are already enough", "start with 1-2 perspectives").
"Enough" sets a floor the model can fall below, and at one tension it did.

Whether the floor should be one is a framework question, not a prompt question,
and it is the question this test answers: `PerspectiveCombination` treats a
single PP as the circular-causality BASE CASE (one Cycle, one self-referencing
Wheel — 2 edges, 1 pair, 2 Transformations), so a 1-PP exploration is
structurally legal. Legal is not the same as useful. If a 1-PP explore produces
transformations and a synthesis, then a decision closed on one tension can still
carry an `adopted_pathway`, and the prompt's floor is wrong. If it produces an
empty shell, the floor is right and the bench flag is measuring the model
correctly declining to build nothing.

Run: poetry run pytest tests/test_single_perspective_explore_real_llm.py -s --real-llm
(Skipped in the default suite — needs a real provider.)
"""

from __future__ import annotations

import json

import pytest

pytestmark = [pytest.mark.real_llm, pytest.mark.llm]

from dialectical_framework.agents.advisor.tools.explore import run_exploration
from dialectical_framework.agents.analyst.skills.expand_polarities import \
    ExpandPolarity
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.polarity import Polarity
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.scope_context import scope

#: The tier the bench flag was measured at — the floor question only matters
#: where the model actually stops at one tension.
WEAK_TIER = "bedrock/global.anthropic.claude-haiku-4-5-20251001-v1:0"

_T_MEANING = "dx://taxonomy/System(General.v1)/Viability/Integrity/Cohesion"
_A_MEANING = "dx://taxonomy/System(General.v1)/Viability/Integrity/Separation"

#: The bench scenario's own tension, so the answer transfers directly to the
#: rows that carry the flag.
T_TEXT = "Buy out the cofounder and take full control"
A_TEXT = "Keep him to retain his customer relationships"


class TestOnePerspectiveIsEnoughToExplore:
    @pytest.mark.asyncio
    @pytest.mark.timeout(1200)
    # Deliberately NOT @traced — serializing `di_container` HANGS (CLAUDE.md).
    async def test_single_perspective_explore_produces_a_pathway(self, di_container):
        from e2e.modelctx import using_model

        case = Case()
        case.commit()

        with scope(case.sid), using_model(di_container, WEAK_TIER):
            t = Statement(text=T_TEXT, meaning=_T_MEANING)
            t.commit()
            a = Statement(text=A_TEXT, meaning=_A_MEANING)
            a.commit()

            polarity = Polarity()
            polarity.set_t(t, heuristic_similarity=1.0)
            polarity.set_a(a, heuristic_similarity=0.8)
            polarity.commit()

            expand = ExpandPolarity(polarity_hash=polarity.hash)
            pps = await expand.resolve()
            assert pps, "ExpandPolarity produced no Perspective — nothing to explore"

            report = await run_exploration(
                perspective_hashes=[pps[0].hash],
                intent="Whether to buy out the cofounder",
                nexus_hash=None,
            )

        print(f"\n--- explore report (1 perspective) ---\n{report}\n")

        # The report IS the seam back to the model (CLAUDE.md: a pipeline's
        # return value is not). Parse what the model would actually see.
        try:
            parsed = json.loads(report)
        except json.JSONDecodeError:
            parsed = {}
        artifacts = parsed.get("artifacts", {}) if isinstance(parsed, dict) else {}
        print(f"artifact keys: {sorted(artifacts)}")

        # A pathway is a Transformation (Ac+/Re+) on a deepened wheel, and the
        # synthesis is what counsel reads from. Assert on the report text rather
        # than artifact names alone — the names have moved before, the presence
        # of a deepened wheel and a synthesis is the durable claim.
        assert "wheel" in report.lower(), (
            "a 1-PP exploration built no wheel — the circular-causality base "
            "case in PerspectiveCombination did not produce a structure, so "
            "the prompt's two-tension floor is load-bearing and the bench's "
            "explore flag is measuring correct model behaviour"
        )
        assert (
            "transformation" in report.lower() or "ac+" in report.lower()
        ), (
            "a 1-PP exploration produced no transformation — there is no "
            "pathway to adopt, so a decision closed on one tension cannot "
            "carry an adopted_pathway ground no matter what the prompt says"
        )
        assert "synthes" in report.lower(), (
            "a 1-PP exploration produced no synthesis — counsel at the closing "
            "turn would have nothing integrated to read from"
        )
