"""Real-LLM check that a tetrad's aspects never collapse into its own poles.

The mocked counterpart (`TestAspectsNeverDedupIntoTheirOwnPoles` in
`test_expand_polarities_count.py`) pins the vocabulary filter and the committed
invariant with a stubbed generator. It cannot show the thing that actually went
wrong live: a REAL model generating a T- whose wording is close enough to T that
`StatementDeduplication` — offered the pole as a candidate — replaces the aspect
with it. The judgement being made there is the deduplicator's, so only a real
provider exercises it.

Why this test exists separately from the weak-tier tripwire
-----------------------------------------------------------
`test_decision_repair_weak_tier.py` is where the collapse was first seen (an
`accepted_cost` ground sitting at `T/T-`), but it reaches ExpandPolarity only if
the weak model happens to call `anchor` — measured `[['anchor']]` on one run and
`[[], [], []]` on the next. A fix verified by a test that runs the fixed code
only sometimes is not verified. This drives `ExpandPolarity` directly, so the
collapse-prone path runs every time.

The pairs are chosen for maximum collapse pressure: each thesis is already
phrased the way an overdevelopment is (a named course of action, absolutes like
"full"/"every"), so the most natural T- the model can write is a near-restatement
of T. That is exactly the live signature — `T: Buy him out for full control now
↔ A: Buy him out for hollow control`, with T and T- the same node.

Run: poetry run pytest tests/test_tetrad_collapse_real_llm.py -s --real-llm
(Skipped in the default suite — needs a real provider.)
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.real_llm, pytest.mark.llm]

from dialectical_framework.agents.analyst.skills.expand_polarities import \
    ExpandPolarity
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.perspective import (POSITION_A_MINUS,
                                                           POSITION_A_PLUS,
                                                           POSITION_T_MINUS,
                                                           POSITION_T_PLUS)
from dialectical_framework.graph.nodes.polarity import Polarity
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.rendering import accepted_cost_condition
from dialectical_framework.graph.scope_context import scope

#: The tier the collapse was measured at. Literal for the same reason the
#: tripwire's is: a weak model writes the sloppiest aspects, which is the
#: pressure this test wants, and it must not weaken because a default moved.
WEAK_TIER = "bedrock/global.anthropic.claude-haiku-4-5-20251001-v1:0"

#: Statement.meaning must be a real taxonomy URI — `lookup_*` raises on
#: unparseable meanings, and the aspect path does reach taxonomy.
_T_MEANING = "dx://taxonomy/System(General.v1)/Viability/Integrity/Cohesion"
_A_MEANING = "dx://taxonomy/System(General.v1)/Viability/Integrity/Separation"

#: (thesis, antithesis) — the live case first, then two more phrased as
#: named courses of action (which classify COMPLEX and are the shape that
#: invites a T- indistinguishable from T).
PAIRS = [
    (
        "Buy out the cofounder and take full control",
        "Keep him to retain his customer relationships",
    ),
    (
        "Ship every feature the biggest customer asks for",
        "Hold the roadmap and let them churn",
    ),
    (
        "Take the funding round now at any terms",
        "Stay bootstrapped and grow slower",
    ),
]


def _pole_hashes(polarity: Polarity) -> dict[str, str]:
    """{'T': hash, 'A': hash} for the polarity's committed poles."""
    out: dict[str, str] = {}
    for label, manager in (("T", polarity.t), ("A", polarity.a)):
        result = manager.get()
        if result:
            node, _rel = result
            out[label] = node.hash
    return out


class TestAspectsStayDistinctFromPolesOnARealModel:
    @pytest.mark.asyncio
    @pytest.mark.timeout(900)
    # Deliberately NOT @traced — it serializes args as span input and
    # `di_container` is cyclic, which HANGS the serializer (CLAUDE.md).
    @pytest.mark.parametrize("t_text,a_text", PAIRS)
    async def test_no_aspect_is_its_own_pole(self, di_container, t_text, a_text):
        from bench.modelctx import using_model

        case = Case()
        case.commit()

        with scope(case.sid), using_model(di_container, WEAK_TIER):
            t = Statement(text=t_text, meaning=_T_MEANING)
            t.commit()
            a = Statement(text=a_text, meaning=_A_MEANING)
            a.commit()

            polarity = Polarity()
            polarity.set_t(t, heuristic_similarity=1.0)
            polarity.set_a(a, heuristic_similarity=0.8)
            polarity.commit()

            poles = _pole_hashes(polarity)

            concern = ExpandPolarity(polarity_hash=polarity.hash)
            pps = await concern.resolve()

            # Collect what actually committed, plus the condition clause the
            # ledger would render for each minus — a collapsed tetrad shows up
            # there as "X is held without X".
            rows: list[tuple[str, str, str, str]] = []
            for pp in pps:
                for position in (
                    POSITION_T_PLUS,
                    POSITION_T_MINUS,
                    POSITION_A_PLUS,
                    POSITION_A_MINUS,
                ):
                    manager = pp.get_relationship_manager_by_position(position)
                    for aspect, _rel in manager.all():
                        condition = (
                            accepted_cost_condition(aspect)
                            if position in (POSITION_T_MINUS, POSITION_A_MINUS)
                            else ""
                        )
                        rows.append(
                            (position, aspect.short_hash, aspect.text, condition)
                        )

        print(f"\nT: {t_text}  [[{t.short_hash}]]")
        print(f"A: {a_text}  [[{a.short_hash}]]")
        for position, short_hash, text, condition in rows:
            print(f"  {position:>8} [[{short_hash}]] {text}{condition}")

        assert pps, "ExpandPolarity produced no Perspective — nothing was tested"
        assert rows, "the Perspective committed with no aspects at any position"

        for position, short_hash, text, condition in rows:
            for label, pole_hash in poles.items():
                assert not pole_hash.startswith(short_hash), (
                    f"{position} deduplicated into the tetrad's own {label} "
                    f"pole — one Statement is now both. Text: {text!r}. This is "
                    f"the collapse that made a decision's accepted cost name "
                    f"the CHOICE instead of its price (see "
                    f"ExpandPolarity._deduplicate_aspects)."
                )

            # The ledger's condition clause must stay a clause. It interpolates
            # the pole and the remedy, and a Statement's DEFAULT format is text
            # PLUS its rationale's explanation — measured live, that put a
            # ~300-word classification essay inside one decision ground, which
            # `one_line()` collapsed rather than dropped. The bound is generous
            # (two headlines ~= `component_length` * 2 words plus the lead-in);
            # it only has to fail on a long-format regression.
            if condition:
                assert len(condition.split()) < 60, (
                    f"the accepted-cost condition for {position} is prose, not "
                    f"a clause — a long-format interpolation regressed: "
                    f"{condition!r}"
                )
