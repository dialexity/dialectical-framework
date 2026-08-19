"""Measure WHY the accepted-cost condition renders on 0/6 live grounds.

`claim2-weak-r5` moved the cost half hard: 6/6 runs recorded an `accepted_cost`,
5/6 on a real risk (T-), and the `T/T-` collapse is gone. But not one of those
Statement grounds carried the condition clause, while the synthetic test renders
it every time. `accepted_cost_condition` blanks when `find_by_statement` reports
anything other than exactly one minus position, so one of three things is true:

  (1) the minus is genuinely shared across two perspectives (commit() dedup on a
      multi-anchor session) — real ambiguity, and the "" is deliberate;
  (2) ONE perspective returns two `T_MINUS` rows because the aspect edge was
      connected twice. CLAUDE.md: `RelationshipManager.connect()` deduplicates
      only `direction="any"` relationships — directed ones silently create
      duplicate edges on repeated calls. That would be a framework bug, and my
      guard would merely be the thing that noticed;
  (3) something else entirely.

The bench cannot tell them apart, because `_ground_position` folds the rel types
into a SET — `['T_MINUS','T_MINUS']` prints as `T-` whether it came from two
perspectives or one edge counted twice. So this probe drives the real anchor path
on one theme (the live shape: several tensions, one topic, shared vocabulary) and
reports, per minus aspect, the number of ROWS, the number of DISTINCT
perspectives, and the rendered condition.

Diagnostic, not a gate — it asserts only that the path produced something to
measure. The number it prints decides which fix is warranted.

Run: poetry run pytest tests/test_condition_ambiguity_live_probe.py -s --real-llm
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.real_llm, pytest.mark.llm, pytest.mark.seam]

from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.perspective import (POSITION_A_MINUS,
                                                           POSITION_T_MINUS)
from dialectical_framework.graph.rendering import accepted_cost_condition
from dialectical_framework.graph.repositories.perspective_repository import \
    PerspectiveRepository
from dialectical_framework.graph.scope_context import scope

WEAK_TIER = "bedrock/global.anthropic.claude-haiku-4-5-20251001-v1:0"

#: The live session's shape: several tensions on ONE theme, anchored in
#: sequence against a growing shared vocabulary. Taken from the bench
#: scenario's own subject matter so the multiplicities transfer.
#: Five, not three: the live runs produced 5-6 perspectives per session, and
#: sharing is a function of how much NEARBY wording the vocabulary already
#: holds. Three well-separated tensions showed no sharing at all (measured);
#: these five are deliberately adjacent — the same buyout seen five ways — which
#: is what a real session's sequence of anchors looks like.
TENSIONS = [
    ("Buy out the cofounder and take full control", "Keep him for his customer relationships"),
    ("Move fast with sole authority", "Keep shared decision-making"),
    ("Protect revenue by keeping him close", "Accept revenue risk to end the drag"),
    ("Own every decision myself", "Share the load with a partner who has checked out"),
    ("End the drag on the company now", "Preserve the relationships that carry the revenue"),
]


class TestLiveConditionAmbiguity:
    @pytest.mark.asyncio
    @pytest.mark.timeout(1200)
    # Deliberately NOT @traced — serializing `di_container` HANGS (CLAUDE.md).
    async def test_report_minus_aspect_multiplicity(self, di_container):
        from e2e.modelctx import using_model

        from dialectical_framework.agents.analyst.skills.expand_polarities import \
            ExpandPolarity
        from dialectical_framework.agents.analyst.skills.introduce_polarity import \
            IntroducePolarity

        case = Case()
        case.commit()

        rows: list[tuple[str, str, int, int, str]] = []

        with scope(case.sid), using_model(di_container, WEAK_TIER):
            for thesis, antithesis in TENSIONS:
                introduce = IntroducePolarity(
                    thesis=thesis, antithesis=antithesis, text=""
                )
                result = await introduce.resolve()
                if not result.primary_polarity_hash:
                    print(f"!! IntroducePolarity produced nothing for {thesis!r}")
                    continue
                await ExpandPolarity(
                    polarity_hash=result.primary_polarity_hash
                ).resolve()

            repo = PerspectiveRepository()
            for pp in repo.find_all_active():
                for position in (POSITION_T_MINUS, POSITION_A_MINUS):
                    manager = pp.get_relationship_manager_by_position(position)
                    for aspect, _rel in manager.all():
                        found = repo.find_by_statement(aspect)
                        minus_rows = [
                            (found_pp, rt)
                            for found_pp, rt in found
                            if rt in ("T_MINUS", "A_MINUS")
                        ]
                        distinct_pps = len({p._id for p, _ in minus_rows})
                        rows.append(
                            (
                                position,
                                aspect.text,
                                len(minus_rows),
                                distinct_pps,
                                accepted_cost_condition(aspect),
                            )
                        )

        print("\nposition | rows | distinct_pps | rendered? | text")
        for position, text, n_rows, n_pps, condition in rows:
            print(
                f"{position:>8} | {n_rows:>4} | {n_pps:>12} | "
                f"{'YES' if condition else ' no'} | {text[:60]}"
            )

        # What the ledger actually renders once the decision names its own
        # tetrad (the repair seam grounds the perspective alongside the cost).
        # This is the fix's own measurement: without siblings these are the
        # rows that blank.
        with scope(case.sid):
            repo = PerspectiveRepository()
            repaired = 0
            for pp in repo.find_all_active():
                for position in (POSITION_T_MINUS, POSITION_A_MINUS):
                    manager = pp.get_relationship_manager_by_position(position)
                    for aspect, _rel in manager.all():
                        if accepted_cost_condition(aspect):
                            continue
                        if accepted_cost_condition(aspect, siblings=[aspect, pp]):
                            repaired += 1
        print(f"blanked rows recoverable via the perspective ground: {repaired}")

        duplicate_edge = [r for r in rows if r[2] > r[3]]
        shared = [r for r in rows if r[3] > 1]
        blanked = [r for r in rows if not r[4]]
        print(f"\nminus aspects examined      : {len(rows)}")
        print(f"condition blanked           : {len(blanked)}")
        print(f"  ...because SHARED (>1 pp) : {len(shared)}")
        print(f"  ...because DUPLICATE EDGES: {len(duplicate_edge)}")
        if duplicate_edge:
            print(
                "  ^ rows > distinct perspectives means one aspect edge was "
                "connected twice — a framework bug (CLAUDE.md, Idempotent "
                "connect), not real ambiguity."
            )

        assert rows, "no minus aspects were produced — nothing was measured"
