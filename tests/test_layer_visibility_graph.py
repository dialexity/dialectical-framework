"""Growing an exploration must not hide the pathways already developed in it.

`DialecticalContext._find_top_layer_cycles` returns cycles at the HIGHEST layer
and falls back to a smaller one only when the top layer is empty. That is right
for the unscoped dump — it is a summary of everything, and the newest layer is
the most complete reading of the case. In ADVISORY MODE it was a quality defect:
the Advisor is pinned to one exploration the person built, and the moment a
Navigator (or its own `explore`) wove in one more tension, a wheel carrying a
written Ac+/Re+ recipe was replaced in the prompt by

    ### Wheel [[...]]
    Pathways: 0/12 (not yet developed)

`_dump_cycle` had already answered this question the other way for the wheel
cap ("the advisory head must not be blind to parts of the deliverable the user
assembled deliberately") — the LAYER selection just never got the same
exemption, and the layer selection is the one that drops finished work.

So advisory mode now also renders earlier layers that carry DEVELOPED pathways.
Developed is the bound: the undeveloped rest stays hidden, which is what keeps
this from re-admitting 96 wheels at k=4.

Three halves this file pins, because each can break without the others:
1. the developed pathway survives growth (the catcher);
2. the undeveloped siblings and layers do NOT come with it, and the unscoped
   dump is untouched;
3. each layer normalises its probabilities WITHIN itself — a shared denominator
   would hand the model a percentage `CausalityEstimation` never computed,
   since it only ever scored same-layer alternatives against each other.
"""

from __future__ import annotations

import uuid

import pytest
from test_dialectical_context import _create_perspective_with_aspects

from dialectical_framework.concerns.dialectical_context import \
    DialecticalContext
from dialectical_framework.graph.estimation_manager import EstimationManager
from dialectical_framework.graph.nodes.cycle import Cycle
from dialectical_framework.graph.nodes.estimation import \
    CausalityProbabilityEstimation
from dialectical_framework.graph.nodes.nexus import Nexus
from dialectical_framework.graph.nodes.rationale import Rationale
from dialectical_framework.graph.nodes.transformation import Transformation
from dialectical_framework.graph.nodes.transition import Transition
from dialectical_framework.graph.nodes.wheel import Wheel
from dialectical_framework.graph.relationships.polarity_relationship import (
    AcPlusRelationship, RePlusRelationship)
from dialectical_framework.graph.scope_context import scope

pytestmark = pytest.mark.llm

#: The Ac+ instruction text, asserted verbatim. A hash would prove the wheel is
#: named; this proves the RECIPE reached the prompt, which is the thing the
#: person built and the thing that was disappearing.
AC_PLUS_TEXT = "Hand the accounts over deliberately"
RE_PLUS_TEXT = "Notice what the handover costs"


def _new_sid() -> str:
    return f"layer-visibility-{uuid.uuid4().hex[:8]}"


def _segments(pp):
    """A perspective's six statements, in T, T+, T-, A, A+, A- order."""
    polarity, _ = pp.polarity.get()
    t, _ = polarity.t.all()[0]
    a, _ = polarity.a.all()[0]
    t_plus, _ = pp.t_plus.all()[0]
    t_minus, _ = pp.t_minus.all()[0]
    a_plus, _ = pp.a_plus.all()[0]
    a_minus, _ = pp.a_minus.all()[0]
    return t, t_plus, t_minus, a, a_plus, a_minus


def _seed_layer(nexus: Nexus, pps: list, name: str, *, wheels: int = 1):
    """A committed Cycle over `pps` with `wheels` committed Wheels under it.

    Sibling wheels differ only by their transitions' nonces, which is enough to
    make them distinct nodes — this file cares about how many are RENDERED, not
    about which arrangement each one encodes.
    """
    cycle = Cycle(intent="preset:balanced")
    cycle.set_perspectives(pps)
    cycle.commit()

    rim = []
    for pp in pps:
        t, _, _, a, _, _ = _segments(pp)
        rim.extend([t, a])

    built = []
    for w in range(wheels):
        wheel = Wheel(intent=f"wheel {name}-{w}")
        wheel.save()
        edges = []
        for i in range(len(rim)):
            edge = Transition(nonce=f"layervis_{name}_{w}_{i}")
            edge.set_source(rim[i]).set_target(rim[(i + 1) % len(rim)])
            edge.commit()
            edge.cycle.connect(wheel)
            edges.append(edge)
        cycle.wheels.connect(wheel)
        wheel.commit()
        built.append((wheel, edges))

    return cycle, built


def _develop(nexus: Nexus, pp, edge, name: str) -> Transformation:
    """One real pathway on `edge` — the Ac+/Re+ recipe a person would recognise."""
    _, t_plus, t_minus, _, a_plus, a_minus = _segments(pp)

    tr = Transformation(intent=f"tr {name}")
    tr.set_nexus(nexus)
    tr.set_on_edge(edge)
    tr.save()

    for source, target, alias, manager, text in (
        (t_minus, a_plus, "Ac+", "ac_plus", AC_PLUS_TEXT),
        (a_minus, t_plus, "Re+", "re_plus", RE_PLUS_TEXT),
    ):
        transition = Transition(nonce=f"layervis_recipe_{name}_{alias}")
        transition.set_source(source).set_target(target)
        transition.instruction = text
        transition.commit()
        rationale = Rationale(text=f"Why {alias} works for {name}")
        rationale.set_explanation_target(transition)
        rationale.commit()
        rel = AcPlusRelationship if alias == "Ac+" else RePlusRelationship
        getattr(tr, manager).connect(transition, relationship=rel(alias=alias))
    tr.commit()
    return tr


def _grown_exploration(*, develop_layer_one: bool = True, layer_one_wheels: int = 1):
    """A layer-1 exploration (optionally developed) that then grew to layer 2.

    This is the shape the defect needed and nothing more: the person built and
    developed one tension, then one more tension arrived.
    """
    nexus = Nexus(intent="whether to take the investment")
    nexus.save()
    nexus.commit()

    pp1 = _create_perspective_with_aspects(
        thesis_text="Ship fast", antithesis_text="Ship safe"
    )
    pp1.nexus.connect(nexus)
    cycle1, built1 = _seed_layer(nexus, [pp1], "L1", wheels=layer_one_wheels)
    if develop_layer_one:
        _develop(nexus, pp1, built1[0][1][0], "L1")

    pp2 = _create_perspective_with_aspects(
        thesis_text="Hire now",
        antithesis_text="Hire later",
        t_plus_text="Capacity ahead of demand",
        t_minus_text="Payroll ahead of revenue",
        a_plus_text="Proof before spend",
        a_minus_text="Opportunity missed while waiting",
    )
    pp2.nexus.connect(nexus)
    cycle2, built2 = _seed_layer(nexus, [pp1, pp2], "L2")

    return nexus, (cycle1, built1), (cycle2, built2)


class TestDevelopedWorkSurvivesGrowth:
    @pytest.mark.asyncio
    async def test_the_recipe_is_still_in_the_counsel_context_after_growth(self):
        """The whole defect in one assertion."""
        with scope(_new_sid()):
            nexus, (cycle1, built1), _ = _grown_exploration()
            rendered = await DialecticalContext(nexus_hash=nexus.hash).resolve()

        assert AC_PLUS_TEXT in rendered and RE_PLUS_TEXT in rendered, (
            "the pathway the person developed vanished from the prompt when the "
            "exploration grew a layer"
        )
        assert built1[0][0].short_hash in rendered
        assert cycle1.short_hash in rendered

    @pytest.mark.asyncio
    async def test_the_new_layer_is_still_rendered_and_still_leads(self):
        """Additive, not a replacement: the top layer keeps its position."""
        with scope(_new_sid()):
            nexus, (cycle1, _), (cycle2, built2) = _grown_exploration()
            rendered = await DialecticalContext(nexus_hash=nexus.hash).resolve()

        assert cycle2.short_hash in rendered
        assert built2[0][0].short_hash in rendered
        assert rendered.index(cycle2.short_hash) < rendered.index(
            cycle1.short_hash
        ), "the earlier layer must come after the top one, not displace it"

    @pytest.mark.asyncio
    async def test_the_earlier_layer_says_what_it_is(self):
        """A second group of percentages needs its own denominator declared.

        Without this line the model reads a layer-1 cycle at 100% next to a
        layer-2 cycle at 63.9% and picks the wrong one — which would be this
        change introducing a reasoning defect while fixing one.
        """
        with scope(_new_sid()):
            nexus, _, _ = _grown_exploration()
            rendered = await DialecticalContext(nexus_hash=nexus.hash).resolve()

        assert "Earlier structure this exploration still carries" in rendered
        assert "1 of 2 tensions" in rendered
        assert "compare within this group only" in rendered


class TestOnlyDevelopedStructureComesBack:
    @pytest.mark.asyncio
    async def test_an_undeveloped_earlier_layer_stays_hidden(self):
        """No pathways developed anywhere below the top: nothing is added."""
        with scope(_new_sid()):
            nexus, (cycle1, built1), _ = _grown_exploration(
                develop_layer_one=False
            )
            rendered = await DialecticalContext(nexus_hash=nexus.hash).resolve()

        assert cycle1.short_hash not in rendered
        assert built1[0][0].short_hash not in rendered
        assert "Earlier structure" not in rendered

    @pytest.mark.asyncio
    async def test_undeveloped_siblings_of_a_developed_wheel_are_named_not_shown(self):
        """The empty shells are the bound on this feature; announce the cut."""
        with scope(_new_sid()):
            nexus, (_, built1), _ = _grown_exploration(layer_one_wheels=3)
            rendered = await DialecticalContext(nexus_hash=nexus.hash).resolve()

        developed, sibling_a, sibling_b = (w for w, _ in built1)
        assert developed.short_hash in rendered
        assert sibling_a.short_hash not in rendered
        assert sibling_b.short_hash not in rendered
        assert "2 wheel(s) at this layer have no pathways developed" in rendered

    @pytest.mark.asyncio
    async def test_the_unscoped_dump_is_untouched(self):
        """No pin, no deliverable: the unscoped summary keeps the top layer only.

        It pays the wheel cap for the same reason, and widening it would grow
        every standalone Advisor prompt for a fidelity obligation it does not
        have.
        """
        with scope(_new_sid()):
            nexus, (cycle1, built1), (cycle2, _) = _grown_exploration()
            rendered = await DialecticalContext().resolve()

        assert cycle2.short_hash in rendered
        assert cycle1.short_hash not in rendered
        assert AC_PLUS_TEXT not in rendered
        assert "Earlier structure" not in rendered


class TestEachLayerNormalisesWithinItself:
    @pytest.mark.asyncio
    async def test_the_top_layer_percentage_is_what_it_was_before_growth(self):
        """Pinned as an EQUALITY against a same-graph render with no pin.

        The unscoped dump renders the top layer alone, so its percentage is the
        single-group answer by construction — if the scoped render agreed with
        it only by accident, a merged denominator would break the tie here.
        """
        with scope(_new_sid()):
            nexus, (cycle1, built1), (cycle2, built2) = _grown_exploration()
            manager = EstimationManager()
            manager.upsert_estimation(cycle1, CausalityProbabilityEstimation, 0.9)
            manager.upsert_estimation(cycle2, CausalityProbabilityEstimation, 0.3)

            scoped = await DialecticalContext(nexus_hash=nexus.hash).resolve()
            unscoped = await DialecticalContext().resolve()

        # Layer 2 is alone in its group either way, so it normalises to 100%.
        assert "P=0.30, 100.0%" in unscoped
        assert "P=0.30, 100.0%" in scoped, (
            "the top layer's percentage moved because an earlier layer joined "
            "its denominator — a comparison CausalityEstimation never made"
        )
        # And the earlier layer normalises inside its own group, not against 1.2.
        assert "P=0.90, 100.0%" in scoped


class TestAnAbandonedWheelIsNotRenderedAtAll:
    """`_get_cycle_wheels` is a TRAVERSAL, so the repository sweep missed it."""

    @pytest.mark.asyncio
    async def test_an_uncommitted_wheel_hanging_off_the_cycle_is_skipped(self):
        with scope(_new_sid()):
            nexus = Nexus(intent="abandoned mid-build")
            nexus.save()
            nexus.commit()
            pp = _create_perspective_with_aspects(
                thesis_text="Ship fast", antithesis_text="Ship safe"
            )
            pp.nexus.connect(nexus)
            cycle, built = _seed_layer(nexus, [pp], "live")

            t_stmt, _, _, a_stmt, _, _ = _segments(pp)
            ghost = Wheel(intent="wheel abandoned")
            ghost.save()
            for i, (source, target) in enumerate(
                ((t_stmt, a_stmt), (a_stmt, t_stmt))
            ):
                edge = Transition(nonce=f"layervis_ghost_{i}")
                edge.set_source(source).set_target(target)
                edge.commit()
                edge.cycle.connect(ghost)
            cycle.wheels.connect(ghost)
            # deliberately never committed

            rendered = await DialecticalContext(nexus_hash=nexus.hash).resolve()

        assert ghost.hash is None, "the fixture must leave the wheel uncommitted"
        assert built[0][0].short_hash in rendered
        # Counted, not matched by hash: an uncommitted wheel has no hash to
        # look for, and both wheels here render the same `Pathways: 0/6` line.
        assert rendered.count("### Wheel") == 1, (
            "an abandoned half-built wheel was rendered into the prompt as an "
            f"arrangement that produced nothing:\n{rendered}"
        )
