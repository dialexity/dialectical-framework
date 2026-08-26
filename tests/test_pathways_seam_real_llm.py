"""The pathway seam, on a real graph: it must READ an arrangement, never build one.

This file used to assert the opposite, and the inversion is deliberate. The
closing's weave sat on the person's wait — `Advisor.chat` awaits the repair
before returning the reply — and per-turn timing on a real provider measured what
that cost: in `timing-check-building` (weak tier, 16 turns) two turns making ZERO
tool calls took 141.9s and 402.0s, of which 127.7s and 387.7s were
`_ensure_pathways_before_closing`. Both landed on the turn immediately before the
closing, the one turn that has to feel exact. So construction moved off the turn;
see that method's docstring for the quality debt this leaves and where it is
recorded.

Still seeded rather than conversational, for the original reason:
`test_pathways_before_closing_weak_tier.py` drives the seam through a real
conversation, which is the honest end-to-end shape but a poor instrument — on its
first run the weak tier anchored only ONE tension across three turns and the test
skipped, which tells us about the `anchor` prompt's productivity, not about the
seam. Seeding two real tensions (real LLM, real graph — the tetrads are genuine,
only the decision to create them is ours) removes everything upstream as a
variable.

What this pins that the DB-free tests cannot, and what survives the inversion:

1. The closing leaves the graph ALONE. A DB-free test can prove the weave
   function was not called; only a real graph can prove no Cycle appeared.
2. `run_exploration_detailed` really accepts these hashes, really writes a Cycle,
   and really leaves those perspectives readable as woven — so
   `is_in_use_by_cycle` does become true. That capability is still needed, just
   off the turn, and a builder whose "already woven" check never becomes true
   would re-explore forever whenever it is finally scheduled.
3. `_existing_pathway_hashes` really finds those transformations afterwards.
   That read is now the closing's ONLY source of a ground, so a silent failure in
   it means every decision closes ungrounded.

    poetry run pytest tests/test_pathways_seam_real_llm.py --real-llm -s
"""

from __future__ import annotations

import pytest

from dialectical_framework.agents.advisor.advisor import Advisor
from dialectical_framework.agents.apps import COUNSELOR_PERSONA
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.repositories.perspective_repository import \
    PerspectiveRepository
from dialectical_framework.graph.scope_context import scope

pytestmark = [pytest.mark.real_llm, pytest.mark.seam]

WEAK_TIER = "bedrock/global.anthropic.claude-haiku-4-5-20251001-v1:0"

#: Two genuinely different oppositions from one case — a pathway is an
#: arrangement BETWEEN tensions, so two same-axis readings would only produce an
#: angle shift (the nexus grouping rule) and would not test weaving.
TENSIONS = [
    ("Buy out the checked-out cofounder", "Keep him and restructure the roles"),
    ("Self-fund the buyout from runway", "Preserve runway for the next hire"),
]


async def _seed_tensions() -> None:
    """Two real tetrads on the current scope. Setup, not the thing under test."""
    from dialectical_framework.agents.analyst.skills.expand_polarities import \
        ExpandPolarity
    from dialectical_framework.agents.analyst.skills.introduce_polarity import \
        IntroducePolarity

    for thesis, antithesis in TENSIONS:
        introduced = await IntroducePolarity(
            thesis=thesis, antithesis=antithesis, text=""
        ).resolve()
        assert introduced.primary_polarity_hash, (
            f"Could not seed the tension {thesis!r} / {antithesis!r} — "
            "this is a setup failure, not a seam failure."
        )
        await ExpandPolarity(
            polarity_hash=introduced.primary_polarity_hash
        ).resolve()


class TestTheClosingReadsAnArrangement:
    @pytest.mark.asyncio
    @pytest.mark.timeout(2400)
    async def test_the_closing_leaves_the_graph_alone_then_reads_what_is_built(
        self, di_container
    ):
        """Two phases, because the two halves fail in opposite directions.

        Phase 1 — the closing over unwoven tensions must add NOTHING. A DB-free
        test can only prove the weave function went uncalled; this proves no Cycle
        appeared, which is the property that actually bounds the turn.

        Phase 2 — weave deliberately, the way deferred construction will, and
        prove the read side then sees it. If phase 2 ever fails while phase 1
        passes, the closing is fast and permanently ungrounded, which is worse
        than slow: nothing errors, the record just quietly never points at a
        recipe.
        """
        from e2e.modelctx import using_model

        from dialectical_framework.agents.advisor.tools.explore import \
            run_exploration_detailed

        case = Case()
        case.commit()

        with scope(case.sid), using_model(di_container, WEAK_TIER):
            await _seed_tensions()

            repo = PerspectiveRepository()
            seeded = repo.find_all_active()
            before = [p for p in seeded if repo.is_in_use_by_cycle(p)]
            assert len(seeded) >= 2, (
                f"Seeding produced {len(seeded)} perspective(s) — too few to "
                "distinguish 'did not weave' from 'had nothing to weave'."
            )
            assert not before, "Setup already wove something — nothing to prove."

            advisor = Advisor(app_preamble=COUNSELOR_PERSONA)
            grounds = await advisor._ensure_pathways_before_closing()

            after_closing = [
                p for p in repo.find_all_active() if repo.is_in_use_by_cycle(p)
            ]
            print(f"\nSeeded perspectives: {len(seeded)}")
            print(f"Woven after the CLOSING: {len(after_closing)}")
            assert not after_closing, (
                f"The closing wove {len(after_closing)} perspective(s) into a "
                "cycle. Construction is back on the person's wait — that is the "
                "387.7s turn, and no comment claiming otherwise makes it free."
            )
            assert grounds == [], (
                f"The closing returned {grounds} over a graph with no "
                "transformations on it — the read is inventing grounds."
            )

            # Phase 2: build it the way the deferral will, off any turn.
            _report, built = await run_exploration_detailed(
                perspective_hashes=[p.hash for p in seeded if p.hash],
                intent=(
                    "Build the causal arrangements over these tensions so a "
                    "closing has a pathway to rest on."
                ),
                nexus_hash=None,
            )
            woven = [p for p in repo.find_all_active() if repo.is_in_use_by_cycle(p)]
            found = advisor._existing_pathway_hashes()

        print(f"Woven after explicit exploration: {len(woven)}")
        print(f"Transformations the read finds:   {len(found)}")

        assert woven, (
            "Explicit exploration over "
            f"{len(seeded)} tensions left NOT ONE in a cycle. Either "
            "run_exploration rejected these hashes or it built structure "
            "`is_in_use_by_cycle` cannot see — in which case any deferred builder "
            "re-explores forever, because its 'already woven' check never becomes "
            "true."
        )
        assert found, (
            f"Exploration reported {len(built)} transformation(s) and "
            "`_existing_pathway_hashes` finds none. That read is the closing's "
            "ONLY source of a ground now, so every decision would close "
            "ungrounded with nothing raising."
        )

    @pytest.mark.asyncio
    @pytest.mark.timeout(2400)
    async def test_the_closing_still_records_the_decision(self, di_container):
        """The r8/wobble_b shape, reproduced deliberately.

        That cell had SIX mapped perspectives, a closing the confirmation check
        calls `confirmed=True, is_recordable=True` when replayed on the same tier
        (`tests/e2e/probe_confirmation_on_r8_wobble_b.py`), and recorded ZERO
        decisions. The hypothesis then was "weaving costs the record", because the
        weave sat BETWEEN the verdict and `RecordDecision` and could have left
        state behind (scope, DI container, conversation).

        The weave is gone from that gap now, which removes the suspect but not the
        test: this is the one failure mode that makes the whole seam a net loss.
        A pathway is worth having; the record is what the person was promised. The
        pathway LOOKUP now sits in that same gap, and a read can fail too.

        The end-to-end conversational tripwire cannot reach this (its weak-tier
        run mapped one tension and the seam correctly stayed silent), so the
        tensions are seeded and the repair is invoked directly.
        """
        from e2e.modelctx import using_model

        from dialectical_framework.graph.repositories.decision_repository import \
            DecisionRepository

        case = Case()
        case.commit()

        with scope(case.sid), using_model(di_container, WEAK_TIER):
            await _seed_tensions()

            repo = PerspectiveRepository()
            assert len(repo.find_all_active()) >= 2, "setup produced too few tensions"

            advisor = Advisor(app_preamble=COUNSELOR_PERSONA)
            # No tool ran this turn, so the repair path is the one under test —
            # exactly the prose-only closing the bench keeps producing.
            await advisor._repair_unrecorded_decision(
                "Yeah, that lands. I'm doing the buyout — settled, not "
                "second-guessing. Write that down as the decision.",
                "**Decision: Cofounder Buyout** You're buying him out this "
                "quarter, self-funded, accepting the runway hit.",
            )

            decisions = DecisionRepository().find_all_active()
            woven = [p for p in repo.find_all_active() if repo.is_in_use_by_cycle(p)]

        print(f"\nWoven after the closing: {len(woven)}")
        print(f"Active decisions: {len(decisions)}")
        for d in decisions:
            print(f"  [[{d.short_hash}]] {d.intent} -> {d.stance}")

        assert decisions, (
            "The RECORD WAS LOST — the r8/wobble_b signature, and the one outcome "
            "that makes this seam a net loss. The weave no longer sits between the "
            "confirmation verdict and RecordDecision, so the remaining suspect in "
            "that gap is the pathway LOOKUP: a read that raises where the old "
            "weave used to is the same bug with a cheaper cause. A record without "
            "a pathway beats a pathway without a record."
        )
        assert not woven, (
            f"The closing wove {len(woven)} perspective(s) — construction is back "
            "on the person's wait; see the sibling test."
        )
