"""Does the pathway seam actually build an arrangement? Seeded, not hoped for.

`test_pathways_before_closing_weak_tier.py` drives the seam through a real
conversation, which is the honest end-to-end shape but a poor instrument: on its
first run the weak tier anchored only ONE tension across three turns, the
two-tension floor correctly kept the seam silent, and the test skipped. That
tells us about the `anchor` prompt's productivity, not about the seam.

So this one seeds two real tensions directly (real LLM, real graph — the tetrads
are genuine, only the decision to create them is ours), then invokes the seam and
asserts the arrangement exists. It is the smallest test that can FAIL if
`_ensure_pathways_before_closing` is broken, because everything upstream of it is
removed as a variable.

What it pins that the DB-free tests cannot: `run_exploration` really accepts the
hashes the seam collects, really writes a Cycle, and really leaves those
perspectives readable as woven — i.e. that `is_in_use_by_cycle`, the seam's own
idempotence check, agrees afterwards with what the seam just built. A seam whose
"already woven" test never becomes true would re-explore on every closing.

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

pytestmark = pytest.mark.real_llm

WEAK_TIER = "bedrock/global.anthropic.claude-haiku-4-5-20251001-v1:0"

#: Two genuinely different oppositions from one case — a pathway is an
#: arrangement BETWEEN tensions, so two same-axis readings would only produce an
#: angle shift (the nexus grouping rule) and would not test weaving.
TENSIONS = [
    ("Buy out the checked-out cofounder", "Keep him and restructure the roles"),
    ("Self-fund the buyout from runway", "Preserve runway for the next hire"),
]


class TestTheSeamBuildsAnArrangement:
    @pytest.mark.asyncio
    @pytest.mark.timeout(2400)
    async def test_two_seeded_tensions_become_a_woven_pathway(self, di_container):
        from bench.modelctx import using_model

        from dialectical_framework.agents.analyst.skills.expand_polarities import \
            ExpandPolarity
        from dialectical_framework.agents.analyst.skills.introduce_polarity import \
            IntroducePolarity

        case = Case()
        case.commit()

        with scope(case.sid), using_model(di_container, WEAK_TIER):
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

            repo = PerspectiveRepository()
            seeded = repo.find_all_active()
            before = [p for p in seeded if repo.is_in_use_by_cycle(p)]
            assert len(seeded) >= 2, (
                f"Seeding produced {len(seeded)} perspective(s); the seam's "
                "two-tension floor makes this unable to assert anything."
            )
            assert not before, "Setup already wove something — nothing to prove."

            advisor = Advisor(app_preamble=COUNSELOR_PERSONA)
            await advisor._ensure_pathways_before_closing()

            after = [p for p in repo.find_all_active() if repo.is_in_use_by_cycle(p)]

        print(f"\nSeeded perspectives: {len(seeded)}")
        print(f"Woven before the seam: {len(before)}")
        print(f"Woven after the seam:  {len(after)}")

        assert after, (
            "The seam ran over "
            f"{len(seeded)} unwoven tensions and NOT ONE ended up in a cycle. "
            "Either run_exploration rejected the hashes the seam collects, or "
            "it built structure that `is_in_use_by_cycle` cannot see — in which "
            "case the seam's own idempotence check never becomes true and it "
            "re-explores on every single closing."
        )

    @pytest.mark.asyncio
    @pytest.mark.timeout(2400)
    async def test_weaving_first_does_not_cost_the_record(self, di_container):
        """The r8/wobble_b shape, reproduced deliberately.

        That cell had SIX mapped perspectives, a closing the confirmation check
        calls `confirmed=True, is_recordable=True` when replayed on the same tier
        (`tests/bench/probe_confirmation_on_r8_wobble_b.py`), and recorded ZERO
        decisions. With six unwoven tensions the pathway seam necessarily fired,
        and it fires BETWEEN the verdict and `RecordDecision` — so "weaving costs
        the record" is the live hypothesis, and it is the one failure mode that
        would make this whole seam a net loss: a pathway is worth having, a
        record is the thing the person was promised.

        The end-to-end conversational tripwire cannot reach this (its weak-tier
        run mapped one tension and the seam correctly stayed silent), so the
        tensions are seeded and the repair is invoked directly.
        """
        from bench.modelctx import using_model

        from dialectical_framework.agents.analyst.skills.expand_polarities import \
            ExpandPolarity
        from dialectical_framework.agents.analyst.skills.introduce_polarity import \
            IntroducePolarity
        from dialectical_framework.graph.repositories.decision_repository import \
            DecisionRepository

        case = Case()
        case.commit()

        with scope(case.sid), using_model(di_container, WEAK_TIER):
            for thesis, antithesis in TENSIONS:
                introduced = await IntroducePolarity(
                    thesis=thesis, antithesis=antithesis, text=""
                ).resolve()
                assert introduced.primary_polarity_hash, "setup failure"
                await ExpandPolarity(
                    polarity_hash=introduced.primary_polarity_hash
                ).resolve()

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
            "Pathways were built and the RECORD WAS LOST. This is the r8/wobble_b "
            "signature and it makes the pathway seam a net loss: it sits between "
            "the confirmation verdict and RecordDecision, so a state it leaves "
            "behind (scope, DI container, conversation) is the suspect. Fix by "
            "recording FIRST and weaving after — a record without a pathway beats "
            "a pathway without a record."
        )
        assert woven, "The seam did not weave — see the sibling test."
