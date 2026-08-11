"""Does `woven` actually become non-zero after the seam weaves? Real graph.

The empty-scope shape is cheap to assert and proves nothing about the interesting
direction. `wove_no_pathway` — and therefore the report's headline validity flag —
now hinges on `woven=N` being non-zero exactly when a pathway exists, so the
count is verified against a graph the seam really wove rather than against a
hand-written summary string. If `is_in_use_by_cycle` and the summary ever disagree,
every future bench row silently mis-flags.

    poetry run pytest tests/bench/probe_graph_summary_on_woven_graph.py --real-llm -s
"""
from __future__ import annotations

import pytest

from bench.config import BenchConfig
from bench.driver import BenchDriver
from bench.modelctx import using_model
from dialectical_framework.agents.advisor.advisor import Advisor
from dialectical_framework.agents.apps import COUNSELOR_PERSONA
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.scope_context import scope

TENSIONS = [
    ("Buy out the checked-out cofounder", "Keep him and restructure the roles"),
    ("Self-fund the buyout from runway", "Preserve runway for the next hire"),
]


@pytest.mark.real_llm
@pytest.mark.asyncio
@pytest.mark.timeout(2400)
async def test_woven_count_tracks_the_seam(di_container) -> None:
    from dialectical_framework.agents.analyst.skills.expand_polarities import \
        ExpandPolarity
    from dialectical_framework.agents.analyst.skills.introduce_polarity import \
        IntroducePolarity

    weak = BenchConfig.from_env(tiers=["weak"]).tiers["weak"]
    case = Case()
    case.commit()

    with scope(case.sid), using_model(di_container, weak):
        for thesis, antithesis in TENSIONS:
            introduced = await IntroducePolarity(
                thesis=thesis, antithesis=antithesis, text=""
            ).resolve()
            assert introduced.primary_polarity_hash, "setup failure"
            await ExpandPolarity(
                polarity_hash=introduced.primary_polarity_hash
            ).resolve()

        before = BenchDriver._graph_summary()
        await Advisor(app_preamble=COUNSELOR_PERSONA)._ensure_pathways_before_closing()
        after = BenchDriver._graph_summary()

    print(f"\nbefore: {before}")
    print(f"after:  {after}")

    assert "woven=0" in before, f"setup already wove something: {before}"
    assert "woven=0" not in after, (
        f"The seam wove and the summary still reports woven=0 ({after}). Every "
        "bench row would be flagged 'NO woven pathway' over a graph that has one "
        "— the exact misreading this instrumentation replaced."
    )
