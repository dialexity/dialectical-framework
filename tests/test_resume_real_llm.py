"""Real-LLM check: a build killed mid-write can be finished, and says it isn't.

Why this can only be measured here
----------------------------------
The resume logic is band arithmetic — "which insight categories does this edge
already carry, and which does it still owe" — and the mock brain returns the
SAME DTO on every call (CLAUDE.md). Under the mock, three Ac+ candidates share
one insight label, so every band question has the same answer and the interesting
states cannot occur. `tests/test_resume_completeness.py` drives the composition
with fakes; this drives the real thing, where the provider picks the level inside
each band and can drift out of the band it was asked for.

The interruption
----------------
`_create_transformation` is capped after `KILL_AFTER` writes. That is the exact
defect site: the tetrads are generated concurrently but written SEQUENTIALLY
(GQLAlchemy is not concurrency-safe), and GQLAlchemy autocommits per node, so a
process that dies part-way through the loop leaves those first writes committed
and nothing else. A killed process and a raised exception leave the graph in the
same state — the graph is the only carrier of resume state, and this test proves
that by resuming through a FRESH skill instance (`run_deepen`), with nothing
handed over in memory.

With the write order being edge A's bands then edge B's, `KILL_AFTER = 4` lands
on the commonest interrupted state and the one the pair-scoping exists for:
**A complete, B part-built.** A tetrad pairs an edge's Ac+ with its partner's Ac+
in the same band, so B's top-up needs A to extract candidates as SUPPORT even
though A owes nothing. Scoped to its own gap, A would sit out, B would find
nobody to pair with, and the top-up would silently generate nothing forever.

Run: poetry run pytest tests/test_resume_real_llm.py -s --real-llm
(Skipped in the default suite — needs a real provider.)
"""

from __future__ import annotations

import json

import pytest

pytestmark = [pytest.mark.real_llm, pytest.mark.llm, pytest.mark.seam]

from dialectical_framework.agents.advisor.tools.deepen import run_deepen
from dialectical_framework.agents.analyst.skills.expand_polarities import \
    ExpandPolarity
from dialectical_framework.agents.explorer.explorer import ExplorationPipeline
from dialectical_framework.agents.explorer.skills.explore_transformations import \
    ExploreTransformations
from dialectical_framework.concerns.ac_re_taxonomy import INSIGHT_CATEGORIES
from dialectical_framework.concerns.create_nexus import CreateNexus
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.polarity import Polarity
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.nodes.wheel import Wheel
from dialectical_framework.graph.rendering import wheel_completeness
from dialectical_framework.graph.repositories.node_repository import \
    NodeRepository
from dialectical_framework.graph.repositories.transformation_repository import \
    TransformationRepository
from dialectical_framework.graph.scope_context import scope

#: Same tier as the 1-PP cardinality check, so the two results are comparable.
WEAK_TIER = "bedrock/global.anthropic.claude-haiku-4-5-20251001-v1:0"

_T_MEANING = "dx://taxonomy/System(General.v1)/Viability/Integrity/Cohesion"
_A_MEANING = "dx://taxonomy/System(General.v1)/Viability/Integrity/Separation"

T_TEXT = "Buy out the cofounder and take full control"
A_TEXT = "Keep him to retain his customer relationships"

#: Writes allowed before the simulated kill. One edge's full band set plus one
#: write on its partner — see the module docstring.
KILL_AFTER = 4

PER_EDGE = len(INSIGHT_CATEGORIES)
EXPECTED = 2 * PER_EDGE


class _SimulatedKill(RuntimeError):
    """Stands in for the process dying inside the sequential write loop."""


def using_model_ctx(di_container):
    from e2e.modelctx import using_model

    return using_model(di_container, WEAK_TIER)


def _artifacts(report: str) -> dict:
    try:
        parsed = json.loads(report)
    except json.JSONDecodeError:
        return {}
    return parsed.get("artifacts", {}) if isinstance(parsed, dict) else {}


def _bands_per_edge(wheel: Wheel) -> dict[str, list[str | None]]:
    """What insight band each edge's committed Transformations landed in."""
    repo = TransformationRepository()
    return {
        edge.short_hash: [
            tr.insight_category for tr in repo.find_by_edge(edge=edge)
        ]
        for edge in wheel.edges
    }


class TestInterruptedBuildResumes:
    @pytest.mark.asyncio
    @pytest.mark.timeout(2400)
    # Deliberately NOT @traced — serializing `di_container` HANGS (CLAUDE.md).
    async def test_killed_mid_write_then_deepened_comes_out_whole(
        self, di_container, monkeypatch
    ):
        case = Case()
        case.commit()

        with scope(case.sid), using_model_ctx(di_container):
            # --- Arrange: a 1-PP wheel with no pathways yet -----------------
            t = Statement(text=T_TEXT, meaning=_T_MEANING)
            t.commit()
            a = Statement(text=A_TEXT, meaning=_A_MEANING)
            a.commit()

            polarity = Polarity()
            polarity.set_t(t, heuristic_similarity=1.0)
            polarity.set_a(a, heuristic_similarity=0.8)
            polarity.commit()

            pps = await ExpandPolarity(polarity_hash=polarity.hash).resolve()
            assert pps, "ExpandPolarity produced no Perspective — nothing to build on"

            created = await CreateNexus().resolve(
                intent="Whether to buy out the cofounder",
                perspective_hashes=[pps[0].hash],
            )
            # max_deep_wheels=0: build the structure, generate no pathways. The
            # interruption below has to happen inside a build this test controls.
            structure = await ExplorationPipeline(
                nexus_hash=created.nexus.short_hash, max_deep_wheels=0
            ).resolve()
            assert structure.wheel_hashes, "no wheel was built — nothing to interrupt"
            wheel_hash = structure.wheel_hashes[0]

            wheel = NodeRepository().find_by_hash(wheel_hash, node_type=Wheel)
            assert wheel is not None
            assert wheel_completeness(wheel).fraction == f"0/{EXPECTED}"

            # --- Act 1: kill the build inside the write loop ----------------
            original_create = ExploreTransformations._create_transformation
            writes = {"n": 0}

            def limited_create(self, nexus, ac_edge, source_segment, target_segment, tetrad):
                if writes["n"] >= KILL_AFTER:
                    raise _SimulatedKill(
                        f"process died after {KILL_AFTER} of {EXPECTED} writes"
                    )
                writes["n"] += 1
                return original_create(
                    self, nexus, ac_edge, source_segment, target_segment, tetrad
                )

            monkeypatch.setattr(
                ExploreTransformations, "_create_transformation", limited_create
            )

            interrupted = ExploreTransformations(wheel_hash=wheel_hash)
            await interrupted.resolve()
            interrupted_report = str(interrupted.report)
            monkeypatch.undo()

            print(f"\n--- interrupted build ---\n{interrupted_report}\n")

            partial = wheel_completeness(wheel)
            print(f"after the kill: {partial.fraction} {_bands_per_edge(wheel)}")

            # The kill is visible, not silent: an edge pair that died mid-write
            # must not render as "0 new, 0 existing" with ok=True.
            assert "FAILED" in interrupted_report, (
                "the interrupted pair reported success — a caller cannot tell a "
                "dead build from a finished one"
            )
            assert partial.done == KILL_AFTER, (
                f"expected exactly {KILL_AFTER} committed transformations after the "
                f"kill, found {partial.done} — autocommit-per-write is what makes "
                f"resume possible, so a different number means the write loop or "
                f"the derived count changed"
            )
            assert not partial.is_complete
            # And it is top-up-able, not blocked: both segments are finished.
            assert partial.incomplete_edges and not partial.blocked_edges

            # --- Act 2: resume through the tool a user would reach for -------
            # Fresh skill instance, nothing carried in memory: the graph is the
            # only state resume reads.
            resumed_report = await run_deepen(wheel_hash)

            final = wheel_completeness(wheel)
            bands = _bands_per_edge(wheel)

        print(f"\n--- resumed deepen ---\n{resumed_report}\n")
        artifacts = _artifacts(resumed_report)
        print(f"artifact keys: {sorted(artifacts)}")
        print(f"after the resume: {final.fraction} {bands}")

        # 1. No band is written twice on an edge. This is the invariant that
        #    cannot be recovered from later: the derived count is per row, so
        #    three Transformations in one band would read 3/3 done while two of
        #    the edge's documented depth alternatives are permanently absent.
        for edge_hash, edge_bands in bands.items():
            mapped = [b for b in edge_bands if b]
            assert len(mapped) == len(set(mapped)), (
                f"edge {edge_hash} carries duplicate insight bands ({edge_bands}) "
                f"— `_only_missing` let two candidates through in one band"
            )
            assert len(edge_bands) <= PER_EDGE, (
                f"edge {edge_hash} carries {len(edge_bands)} transformations, "
                f"more than the per-edge budget of {PER_EDGE} — the resume "
                f"re-added bands it already had"
            )

        # 2. The survivors were reused, not rebuilt.
        assert int(artifacts.get("existing_count", 0)) >= KILL_AFTER, (
            f"only {artifacts.get('existing_count')} transformations were reused, "
            f"but {KILL_AFTER} survived the kill — the resume rebuilt work that "
            f"was already committed"
        )

        # 3. The top-up reads as a top-up.
        assert "resumed_categories" in artifacts, (
            "a part-built edge was completed but the report does not say it was a "
            "resume — the agent cannot tell this from a fresh build"
        )

        # 4. It came out whole. If this fails, read `still_missing` first: a
        #    reported shortfall means the provider answered outside the bands it
        #    was asked for (honest, and topped up by another deepen); its ABSENCE
        #    together with a short wheel is the silent-partial defect itself.
        assert final.fraction == f"{EXPECTED}/{EXPECTED}", (
            f"resumed wheel is {final.fraction}, not whole — "
            f"still_missing={artifacts.get('still_missing')}, bands={bands}"
        )
        assert artifacts.get("pathway_completeness") == f"{EXPECTED}/{EXPECTED}"
        assert "still_missing" not in artifacts

        # 5. The synthesis over the finished wheel is stamped whole, and is not
        #    announced as a fragment.
        assert artifacts.get("completeness") == f"{EXPECTED}/{EXPECTED}", (
            f"synthesis stamp is {artifacts.get('completeness')} — S+ emerges from "
            f"ALL transformations at once, so the stamp must record the whole wheel"
        )
        assert "PARTIAL" not in resumed_report
        assert "synthesis_skipped" not in artifacts
