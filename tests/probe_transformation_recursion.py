"""Probe: does the coarser-layer refinement context ever reach a Transformation?

WHY THIS IS FREE
================
The theory says a finer pathway is a REFINEMENT of a coarser one: with one
perspective the move might be "find a friend", and with three it becomes "find a
colleague who could be your friend". `transformation_generation.py` implements
exactly that — it asks `TransformationRepository.find_parent_transformations` for
the coarser-layer parents of the edge it is about to detail, and
`_build_coarser_context` renders their `Action:` / `Reflection:` instructions
coarsest-first, indented by layer, into the prompt.

**Whether that lookup returns anything is decided entirely by the graph** — which
wheels exist, which of them carry Transformations, and which statements their edges
run between. No provider is involved in any of it. So mock brain reproduces the
mechanism at zero cost, and the one question worth asking first is answerable for
free: on the path the Advisor actually takes, does the recursion fire at all?

WHAT IT MEASURES
================
Two arms, each on its own Case so nothing is reused between them, both over the
same `K` tensions:

1. **direct** — build all wheels, then deepen ONLY the top-layer wheel. This is the
   Advisor's `explore` policy (`EXPLORE_DEEP_WHEELS = 1`, and `_select_deep_wheels`
   ranks layer-first), and it is what a person gets from one tool call.
2. **climb** — build all wheels, then deepen one wheel per layer, ascending: layer
   1, then 2, ... then the top. Each rung is a finished answer in its own right, and
   each is in the graph before the next one is generated.

For every `find_parent_transformations` call in both arms it records the layer of
the edge that asked, how many parents came back, and which layers they came from.
The rendered context string is captured verbatim.

It also reports WHICH of the generation calls in a tetrad receive the context, by
signature — see the third finding, which is the one this probe was not looking for.

    poetry run pytest tests/probe_transformation_recursion.py -s
    DIALEXITY_PROBE_TR_K=2 poetry run pytest tests/probe_transformation_recursion.py -s

WHAT IT CANNOT SAY
==================
Mock brain returns the SAME DTO for every call, so every Ac+ headline in the run is
the same string. That is fine for the question asked here — presence, layer depth,
and rendering shape are all structural — and useless for the question that follows:
whether a parent's wording actually makes the child's wording more specific. That
one needs a provider and a human reading two Ac+ statements side by side.

It also does not measure wall clock worth quoting. Deepening under mock brain is
graph writes and python; the call COUNT is the transferable figure (multiply by the
archived paid mean if you want an order of magnitude). **And the absolute counts are
about a THIRD of paid**, because mock brain returns one DTO so `_missing_categories`
collapses and each edge gets 1 Transformation instead of `|INSIGHT_CATEGORIES|` = 3.
The RATIO between the arms survives that, since both collapse identically and the
cost of either arm is driven by its edge count.

RESULTS
=======
2026-09-11, mock brain, k=2 (28s) and k=4 (268s).

    k=4, wheels built by layer: {1: 4, 2: 12, 3: 32, 4: 48}

                            rungs  edges  transf  lookups  calls
    direct (Advisor path)       1      8       8        8     64
    climb (layer 1 -> top)      4     20      20       20    160

**1. On the Advisor's path the recursion never fires. 0 of 8 lookups found a
parent, at both k=2 and k=4.** `_build_coarser_context` returned `None` every time,
so the prompt's `<broader_journey>` section did not exist and the MOST detailed
pathway in the exploration was generated with no refinement context at all. Nothing
is wrong with the lookup — `explore` deepens one wheel (`EXPLORE_DEEP_WHEELS = 1`)
and `_select_deep_wheels` ranks layer-first, so on a fresh nexus no coarser wheel
has a Transformation to be a parent OF. (A person who has previously used `deepen`
on coarser wheels is a different case, and gets a different answer.)

**2. Under a climb it fires, and the chain is transitive exactly as documented.**
Parents by asking layer at k=4: layer 2 sees `[1]`, layer 3 sees `[1, 2]`, layer 4
sees `[1, 2, 3]` — up to 7 parents for one edge, rendered coarsest-first and
indented per layer. 18 of 20 lookups found a parent (the 2 that did not are the
layer-1 rung, which has no coarser layer by definition). **So the climb is not a UX
preference — it is the precondition for the recursion existing at all.**

**3. The finding this probe was not looking for: `parent_context` reaches exactly
ONE of the five generation calls, and it is not one of the two the theory is
about.** By signature:

    no    ActionExtraction.resolve                 (produces Ac+)
    YES   TransformationGeneration._generate_ac_minus       (Ac-)
    no    TransformationGeneration._generate_re_side  (Re+, Re-)
    no    TransformationGeneration._score_hs                (HS)
    no    TransformationGeneration._generate_category_reframings (Ac, Re)

Ac+ is produced by `ActionExtraction` and copied into the tetrad VERBATIM
(`ac_plus_dto` is built field-for-field off the candidate), so even on a climb the
"find a friend" -> "find a colleague who could be your friend" refinement has no
route into Ac+. Re+ is generated by `_generate_re_side`, which is not passed it
either. Only the Ac- overshoot sees the broader journey. **This is a separate defect
from (1) and fixing (1) alone would not produce the refinement the theory
describes.**

**4. The climb costs 2.5x the calls of the direct path (160 against 64 at k=4)** and
that is the whole price — no transformation is reused between rungs (20 edges, 20
Transformations), because a `Transition` carries a nonce and belongs to exactly one
container. What the ratio does not show is that the climb spends it across FOUR
finished answers instead of one, so the person's first wait is one rung.
"""

from __future__ import annotations

import os
import time
from inspect import signature

import pytest

import mock_brain as mock_brain_module
from dialectical_framework.agents.explorer.skills.build_wheels import BuildWheels
from dialectical_framework.agents.explorer.skills.explore_transformations import \
    ExploreTransformations
from dialectical_framework.concerns.action_extraction import ActionExtraction
from dialectical_framework.concerns.create_nexus import CreateNexus
from dialectical_framework.concerns.transformation_generation import \
    TransformationGeneration
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.repositories.transformation_repository import \
    TransformationRepository
from dialectical_framework.graph.repositories.wheel_repository import \
    WheelRepository
from dialectical_framework.graph.scope_context import scope
from probe_build_wheels_offprovider import INTENT, TENSIONS, _perspectives

#: 4 is the app's own cap on perspectives and the size the question is about, so it
#: is the default here rather than the sibling probes' quick 2 — the transitive
#: chain (layer 1 -> 2 -> 3) only has room to appear above k=2. Bounded by the
#: tension list, since structural dedup is per-content.
K = max(2, min(len(TENSIONS), int(os.getenv("DIALEXITY_PROBE_TR_K", "4"))))

#: `tests/e2e/probe_explore_cost.py`, 2026-08-29, weak tier. Turns a call count into
#: an order of magnitude of provider time — one archived tier, not a wall clock.
PAID_MEAN_CALL_S = 5.5


class _Counter:
    """Every formatted provider call, grouped by the DTO it was asked for."""

    def __init__(self) -> None:
        self.by_format: dict[str, int] = {}

    @property
    def total(self) -> int:
        return sum(self.by_format.values())

    def add(self, name: str) -> None:
        self.by_format[name] = self.by_format.get(name, 0) + 1


def _count_calls(patch, counter: _Counter) -> None:
    """Wrap the one funnel every mocked formatted call goes through.

    `build_mock_response` is looked up in the `mock_brain` module namespace when the
    patched `use_brain` wrapper runs, so setting it here reaches the mock the
    autouse fixture installed earlier.
    """
    original = mock_brain_module.build_mock_response

    def wrapper(format_model, *args, **kwargs):
        counter.add(getattr(format_model, "__name__", str(format_model)))
        return original(format_model, *args, **kwargs)

    patch.setattr(mock_brain_module, "build_mock_response", wrapper)


class _Lookups:
    """One row per `find_parent_transformations` call."""

    def __init__(self) -> None:
        self.rows: list[dict] = []
        self.contexts: list[tuple[int, str]] = []

    def by_layer(self) -> dict[int, list[dict]]:
        grouped: dict[int, list[dict]] = {}
        for row in self.rows:
            grouped.setdefault(row["layer"], []).append(row)
        return grouped


def _watch_parent_lookups(patch, record: _Lookups) -> None:
    """Record what the recursion was asked and what it answered.

    The asking edge's layer is read through the repository's own
    `_resolve_wheel`, so a row is labelled by the same wheel the lookup itself
    used to decide whether to recurse at all.
    """
    original_find = TransformationRepository.find_parent_transformations

    def find_wrapper(self, *args, **kwargs):
        edge = kwargs.get("edge") or args[0]
        parents = original_find(self, *args, **kwargs)
        wheel = self._resolve_wheel(edge)
        record.rows.append({
            "layer": wheel.polarity_count if wheel else 0,
            "edge": edge.short_hash,
            "parents": len(parents),
            "parent_layers": sorted({ct.layer for ct in parents}),
        })
        return parents

    original_build = TransformationGeneration._build_coarser_context

    def build_wrapper(self, parents):
        rendered = original_build(self, parents)
        if rendered:
            depth = len({ct.layer for ct in parents})
            record.contexts.append((depth, rendered))
        return rendered

    patch.setattr(
        TransformationRepository, "find_parent_transformations", find_wrapper
    )
    patch.setattr(
        TransformationGeneration, "_build_coarser_context", build_wrapper
    )


async def _build(nexus_hash: str) -> None:
    await BuildWheels(nexus_hash=nexus_hash).resolve()


def _wheels_by_layer(nexus) -> dict[int, list]:
    """Every wheel under the nexus, grouped by its cycle's perspective count."""
    grouped: dict[int, list] = {}
    for cycle, wheel in WheelRepository().find_by_nexus(nexus):
        grouped.setdefault(len(cycle.perspective_hashes), []).append(wheel)
    return grouped


async def _run_arm(label: str, climb: bool, monkeypatch) -> dict:
    """Build once, then deepen either the top wheel or one wheel per layer."""
    case = Case()
    case.commit()
    with scope(case.sid):
        hashes = await _perspectives(K)
        created = await CreateNexus().resolve(
            intent=INTENT, perspective_hashes=hashes
        )
        await _build(created.nexus.hash)

        by_layer = _wheels_by_layer(created.nexus)
        top = max(by_layer)
        # First wheel at each layer, which is `find_by_nexus`' own committed_at/id
        # order. NOT `_select_deep_wheels`' plausibility ranking — under mock brain
        # every wheel scores identically, so ranking would pick arbitrarily and the
        # two arms could disagree about which wheel is "the top one".
        layers = sorted(by_layer) if climb else [top]
        chosen = [(layer, by_layer[layer][0]) for layer in layers]

        record = _Lookups()
        counter = _Counter()
        deepened: list[dict] = []
        with monkeypatch.context() as patch:
            _count_calls(patch, counter)
            _watch_parent_lookups(patch, record)
            started = time.monotonic()
            for layer, wheel in chosen:
                before = len(record.rows)
                result = await ExploreTransformations(
                    wheel_hash=wheel.hash
                ).resolve()
                deepened.append({
                    "layer": layer,
                    "wheel": wheel.short_hash,
                    "edges": len(wheel.edges),
                    "transformations": len(result.all),
                    "lookups": len(record.rows) - before,
                })
            wall = time.monotonic() - started

    return {
        "label": label,
        "wheel_counts": {layer: len(ws) for layer, ws in sorted(by_layer.items())},
        "top": top,
        "deepened": deepened,
        "record": record,
        "calls": counter.total,
        "by_format": counter.by_format,
        "wall": wall,
    }


def _print_arm_table(arms: list[dict]) -> None:
    print(
        f"\n  {'':<26}{'rungs':>7}{'edges':>7}{'transf':>8}"
        f"{'lookups':>9}{'calls':>7}{'off-provider':>14}"
    )
    for arm in arms:
        edges = sum(d["edges"] for d in arm["deepened"])
        transf = sum(d["transformations"] for d in arm["deepened"])
        print(
            f"  {arm['label']:<26}{len(arm['deepened']):>7}{edges:>7}{transf:>8}"
            f"{len(arm['record'].rows):>9}{arm['calls']:>7}{arm['wall']:>13.2f}s"
        )


def _print_lookup_table(arm: dict) -> None:
    print(f"\n  PARENT LOOKUPS — {arm['label']}")
    print(
        f"       {'asking layer':>13}{'lookups':>9}{'with parents':>14}"
        f"{'parents (max)':>15}   parent layers seen"
    )
    grouped = arm["record"].by_layer()
    for layer in sorted(grouped):
        rows = grouped[layer]
        hit = [r for r in rows if r["parents"]]
        seen = sorted({lyr for r in rows for lyr in r["parent_layers"]})
        biggest = max((r["parents"] for r in rows), default=0)
        note = "" if seen else "   (nothing to refine from)"
        print(
            f"       {layer:>13}{len(rows):>9}{len(hit):>14}{biggest:>15}"
            f"   {seen or '-'}{note}"
        )


@pytest.mark.llm
@pytest.mark.asyncio
async def test_probe_whether_the_coarser_context_ever_arrives(
    di_container, monkeypatch
):
    print(
        f"\n### coarser-layer refinement context at k = {K} perspectives, LLM"
        f" mocked (DIALEXITY_PROBE_TR_K to change)"
    )

    direct = await _run_arm("direct (Advisor path)", climb=False, monkeypatch=monkeypatch)
    climb = await _run_arm("climb (layer 1 -> top)", climb=True, monkeypatch=monkeypatch)
    arms = [direct, climb]

    print(f"\n  wheels built, by layer: {direct['wheel_counts']}")
    _print_arm_table(arms)

    for arm in arms:
        _print_lookup_table(arm)

    print("\n  RUNGS, in the order they were deepened")
    for arm in arms:
        for rung in arm["deepened"]:
            print(
                f"       {arm['label']:<26} layer {rung['layer']}"
                f"  wheel {rung['wheel']}  {rung['edges']} edges"
                f"  {rung['transformations']} transformations"
            )

    for arm in arms:
        contexts = arm["record"].contexts
        if not contexts:
            print(
                f"\n  RENDERED CONTEXT — {arm['label']}: NONE."
                f" `_build_coarser_context` returned None every time, so the"
                f" prompt's <broader_journey> section did not exist."
            )
            continue
        depth, rendered = max(contexts, key=lambda pair: pair[0])
        print(
            f"\n  RENDERED CONTEXT — {arm['label']}"
            f" ({len(contexts)} built, deepest spans {depth} layer(s)):"
        )
        for line in rendered.splitlines():
            print(f"       |{line}")
        print(
            "       (every instruction reads the same because mock brain returns"
            " one DTO — the SHAPE is what this shows)"
        )

    # Which calls in a tetrad can even see it. Read off the signatures rather than
    # asserted from the code being read once, because this is the finding most
    # likely to change without anyone thinking about this probe.
    print("\n  WHICH GENERATION CALLS CAN RECEIVE THE CONTEXT")
    candidates = [
        ("ActionExtraction.resolve            (produces Ac+)",
         ActionExtraction.resolve),
        ("TransformationGeneration._generate_ac_minus  (Ac-)",
         TransformationGeneration._generate_ac_minus),
        ("TransformationGeneration._generate_re_side   (Re+, Re-)",
         TransformationGeneration._generate_re_side),
        ("TransformationGeneration._score_hs           (HS)",
         TransformationGeneration._score_hs),
        ("TransformationGeneration._generate_category_reframings (Ac, Re)",
         TransformationGeneration._generate_category_reframings),
    ]
    for name, fn in candidates:
        takes = "parent_context" in signature(fn).parameters
        print(f"       {'YES' if takes else ' no'}   {name}")

    total_direct = direct["calls"]
    total_climb = climb["calls"]
    print(
        f"\n  The climb costs {total_climb / max(total_direct, 1):.1f}x the calls"
        f" ({total_climb} against {total_direct}), which at the archived paid mean"
        f" of {PAID_MEAN_CALL_S}s is ~{total_climb * PAID_MEAN_CALL_S / 60:.0f}"
        f" minutes of provider time against"
        f" ~{total_direct * PAID_MEAN_CALL_S / 60:.0f} — spread over"
        f" {len(climb['deepened'])} moments a person is already reading, instead of"
        f" one."
    )

    direct_hits = [r for r in direct["record"].rows if r["parents"]]
    climb_hits = [r for r in climb["record"].rows if r["parents"]]
    assert direct["record"].rows, (
        "the direct arm made no parent lookups at all, so it deepened nothing"
        " — the arm is broken, not the recursion"
    )
    # Only the CLIMB half is asserted. The direct arm finding 0 parents is the
    # defect this probe exists to show, not a behaviour to pin — asserting it would
    # make a future fix fail here. The climb half is the opposite: if the recursion
    # stops firing even when the parents are sitting in the graph, the whole
    # mechanism is dead and every number above is meaningless.
    assert climb_hits, (
        "the climb found no parents either, so `find_parent_transformations` is not"
        " returning coarser Transformations even when they exist — the mechanism is"
        " broken, and finding (1) above can no longer be read as a policy problem"
    )
    assert max(r["parents"] for r in climb_hits) > 1 or K < 3, (
        "no edge saw more than one parent at k >= 3, so the RECURSION (layer 1 up to"
        " L-1, chained transitively) has collapsed to a single-layer lookup"
    )
    print(
        f"\n  direct: {len(direct_hits)} of {len(direct['record'].rows)} lookups"
        f" found a parent."
        f"\n  climb:  {len(climb_hits)} of {len(climb['record'].rows)} lookups"
        f" found a parent."
    )
