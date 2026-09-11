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

1. **direct** — `ExplorationPipeline(max_deep_wheels=1, refine_from_coarser=False)`:
   build all wheels, deepen ONLY the top-plausibility one. This was the Advisor's
   `explore` policy until 2026-09-11, and it is still the headless default.
2. **climb** — the same pipeline with `refine_from_coarser=True`, which is what the
   Advisor now passes (`EXPLORE_REFINE_FROM_COARSER`): the top wheel plus one
   ancestor per layer below it, deepened coarsest-first, each rung committed before
   the next is generated. Each rung is a finished answer in its own right.

Both arms drive the SHIPPED pipeline rather than picking wheels themselves. The
thing under measurement IS the wheel-selection policy, so a probe that selected its
own wheels could not be wrong about it — and the first version of this file did
exactly that, which is why the numbers below moved when it was rewired.

For every `find_parent_transformations` call in both arms it records the layer of
the edge that asked, how many parents came back, and which layers they came from.
The rendered context string is captured verbatim.

It also reports which of the generation calls in a tetrad receive the context — both
by signature and by what each one could actually SEE when it ran, which are not the
same list. See the third finding, the one this probe was not looking for.

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
2026-09-11, mock brain, through the shipped pipeline, k=2 (13s) and k=4 (204s).

    k=4, wheels built by layer: {1: 4, 2: 12, 3: 32, 4: 48}

                            rungs  edges  transf  lookups  calls  off-provider
    direct (Advisor path)       1      8       8        8    177        96.39s
    climb (layer 1 -> top)      4     20      20       20    273       101.74s

**1. Without the climb the recursion never fires. 0 of 8 lookups found a parent, at
both k=2 and k=4.** `_build_coarser_context` returned `None` every time, so the
prompt's `<broader_journey>` section did not exist and the MOST detailed pathway in
the exploration was generated with no refinement context at all. Nothing was ever
wrong with the lookup: one wheel deepened on a fresh nexus leaves no coarser wheel
carrying a Transformation to be a parent OF. This was the Advisor's path until
2026-09-11 and is what `refine_from_coarser=False` still does, so it is the arm the
fix is measured against, not a bug report. (A person who had previously used
`deepen` on coarser wheels was a different case, and got a different answer.)

**2. With it, the chain is transitive exactly as documented.** Parents by asking
layer at k=4: layer 2 sees `[1]`, layer 3 sees `[1, 2]`, layer 4 sees `[1, 2, 3]` —
up to 7 parents for one edge, rendered coarsest-first and indented per layer. 18 of
20 lookups found a parent (the 2 that did not are the layer-1 rung, which has no
coarser layer by definition). **So the climb was never a UX preference — it is the
precondition for the recursion existing at all.**

**2b. It costs less than deepening one wheel three times over would suggest: 1.5x
the provider calls, not 2.5x.** The edge count does go up 2.5x (20 against 8), but a
run is not only its deepening — building and estimating all 96 wheels at k=4 is paid
by both arms, so the marginal cost lands at 273 calls against 177. Off-provider wall
clock barely moves at all (101.74s against 96.39s, ~5%), which says the same thing
from the graph side: at k=4 the fixed structural work dominates. And the 96 extra
calls are ordered smallest-wheel-first, so the first finished pathway arrives EARLIER
than the single-wheel arm's does, not later.

**3. The finding this probe was not looking for, and the reason it is measured
rather than read: BEING IN THE CONTEXT WINDOW IS NOT BEING ASKED. Fixed
2026-09-11; the table below is what it looked like before, and it is why the
assertion now reads the PROMPT and not visibility.** `parent_context` used to be a
parameter of exactly one of the five generation calls:

    no    ActionExtraction.resolve                 (produces Ac+)
    YES   TransformationGeneration._generate_ac_minus       (Ac-)
    no    TransformationGeneration._generate_re_side  (Re+, Re-)
    no    TransformationGeneration._score_hs                (HS)
    no    TransformationGeneration._generate_category_reframings (Ac, Re)

**Reading that table as "only Ac- is refined" is wrong, and this probe reported it
that way on its first run.** `TransformationGeneration` creates ONE
`ConversationFacilitator` in `__init__` and all four of its calls submit to that
same conversation, so the `<broader_journey>` block stays in the context window.
Measured per submit, before the fix:

    response model              in its prompt   in history
    AcMinusCompletionDto                  YES           no
    ReSideCompletionDto                    no          YES
    HsScoringDto                           no          YES
    CategoryReframingDto                   no          YES

So Re+/Re- were never BLIND — they were UNASKED. They saw the coarser hierarchy and
its instruction, by history rather than by parameter, which made refinement an
accident of ordering: Ac- happened to run first, nothing enforced that, and an
`isolate()` on any later call would have dropped it with every signature untouched.
Re+/Re- are now handed `parent_context` and told which line of the hierarchy they
descend from (a parent Transformation carries BOTH spiral directions, so its
`Reflection:` line is the coarser reflection for the same edge).

**Ac+ was the genuine hole, and it is exactly the position the theory's example is
about.** `ActionExtraction` has its OWN facilitator and submits through `isolate()`,
so nothing accumulates there; it ran in Phase 1, before any parent lookup happened
at all; and its candidate is copied into the tetrad verbatim (`ac_plus_dto` is built
field-for-field off it). So "find a friend" -> "find a colleague who could be your
friend" had no route into Ac+ even on a climb — the tetrad's LEADING position, the
generative one, refined nothing however much context the three later calls got. The
lookup now happens once per edge in `_phase1_for_edge` and is carried to both phases
on `_EdgeProcessingData`, which is also a net REDUCTION in queries: Phase 2 runs per
CANDIDATE, so the lookup it used to do itself was three identical questions an edge.

**HS scoring and the category reframings are still deliberately not asked**, and the
assertion pins that too: HS is rendered to the advisor as evidence (it does NOT
gate — `HS_THRESHOLD` is polarity-level only), so biasing a judgement with "be more
concrete than the broader path" is a different class of defect, and the reframings
derive from positions that are already refined.

Measured after the fix, k=4 climb arm, per response model across the whole run —
`asked` = the section was in that call's OWN prompt, `history only` = it could see
it but nothing pointed at it:

    response model              calls  asked  history only
    ActionCandidateDto             60     54             0
    AcMinusCompletionDto           20     18             0
    ReSideCompletionDto            20     18             0
    HsScoringDto                   20      0            18
    CategoryReframingDto           20      0            18

18 of 20 edges have ancestry (the 2 that do not are the layer-1 rung), and 54 = 18 x
3 insight categories — so every generative position is asked on exactly the edges
that have a broader path, and on all of them. **The assertion is that RATIO, not
"every call carries it"**: a layer-1 wheel's prompt is correctly bare, because
`coarser_journey_section` returns `""` rather than a "no parents" note.

**The lookup count is a net REDUCTION, and the table above is where to see it: 20
lookups for 20 edges.** `_generate_tetrad` runs per CANDIDATE, so the lookup
`TransformationGeneration` used to do itself was three identical queries an edge;
hoisting it into `_phase1_for_edge` makes it one, even after adding Ac+. Cost in
provider calls is unchanged (273 against 177) — this fix adds prompt text, not
calls.

**4. Nothing is reused between rungs: 20 edges produce 20 Transformations.** A
`Transition` carries a nonce and belongs to exactly one container, so wheels at
different layers never share one. That is why the edge count is the cost model (see
2b for what it comes to as a fraction of a whole run), and why a rung cannot be made
cheaper by hoping the layer below already covered it.
"""

from __future__ import annotations

import itertools
import os
import time
from inspect import signature

import pytest

import mock_brain as mock_brain_module
from dialectical_framework.agents.explorer.explorer import ExplorationPipeline
from dialectical_framework.concerns import \
    transformation_generation as transformation_generation_module
from dialectical_framework.concerns.action_extraction import ActionExtraction
from dialectical_framework.concerns.create_nexus import CreateNexus
from dialectical_framework.concerns.transformation_generation import \
    TransformationGeneration
from dialectical_framework.utils import edge_context as edge_context_module
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

    original_build = edge_context_module.build_coarser_context

    def build_wrapper(parents):
        rendered = original_build(parents)
        if rendered:
            depth = len({ct.layer for ct in parents})
            record.contexts.append((depth, rendered))
        return rendered

    patch.setattr(
        TransformationRepository, "find_parent_transformations", find_wrapper
    )
    # Two module attributes for ONE function. The renderer lives in
    # `utils/edge_context.py` (it was `TransformationGeneration._build_coarser_context`
    # until 2026-09-11, when Ac+ started needing it too and a shared home became the
    # only non-circular one). `explore_transformations` imports it INSIDE
    # `_phase1_for_edge`, so it resolves the patched attribute at call time and the
    # first line here is what catches the shipped path; `transformation_generation`
    # binds it at module import, so its own fallback lookup — the one a direct caller
    # that passes no `parent_context` still takes — needs its own patch or this probe
    # would under-count silently.
    patch.setattr(edge_context_module, "build_coarser_context", build_wrapper)
    patch.setattr(
        transformation_generation_module, "build_coarser_context", build_wrapper
    )


#: The marker `_generate_ac_minus` wraps the coarser context in. Searched for in the
#: RENDERED prompt and in the conversation's accumulated history, because a
#: signature check cannot see history and this probe first reported the wrong answer
#: by trusting one.
_MARKER = "<broader_journey>"


class _Exposure:
    """Per conversation, what each submit could actually see.

    A signature says which call is HANDED the context. It does not say which calls
    can READ it: `TransformationGeneration` creates ONE `ConversationFacilitator` in
    `__init__` and every one of its calls submits to that same conversation, so
    anything in an earlier user message is still in the context window of every
    later one. `ActionExtraction` is the opposite — its own facilitator, and it
    submits through `isolate()`, so nothing accumulates there at all.
    """

    def __init__(self) -> None:
        #: token -> [(response model, in this prompt, already in history)]
        self.by_conversation: dict[int, list[tuple[str, bool, bool]]] = {}

    def record(
        self, conversation_id: int, model: str, in_prompt: bool, in_history: bool
    ) -> None:
        self.by_conversation.setdefault(conversation_id, []).append(
            (model, in_prompt, in_history)
        )

    def with_marker(self) -> list[list[tuple[str, bool, bool]]]:
        """Only the conversations where the context appeared at all."""
        return [
            rows for rows in self.by_conversation.values()
            if any(in_prompt or in_history for _, in_prompt, in_history in rows)
        ]


def _watch_exposure(patch, record: _Exposure) -> None:
    """Wrap `submit` to ask, per call, what the model was actually looking at."""
    from dialectical_framework.agents.conversation_facilitator import \
        ConversationFacilitator

    original = ConversationFacilitator.submit
    counter = itertools.count(1)

    async def wrapper(self, response_model, user_content, *args, **kwargs):
        # A stamped token, NOT `id(self)`: CPython reuses the address of a freed
        # object, and one `TransformationGeneration` per edge means they are freed
        # constantly — grouping by `id` merged two edges' conversations into one
        # apparent conversation whose history looked like it had been reset
        # mid-stream. The per-row booleans below were unaffected, but the grouping
        # they are read under is the whole claim, so it has to be stable.
        token = getattr(self, "_probe_conversation_token", None)
        if token is None:
            token = next(counter)
            self._probe_conversation_token = token
        # BEFORE the call, because `submit` appends the new user message itself.
        in_history = _MARKER in str(self._messages)
        in_prompt = _MARKER in str(user_content)
        record.record(
            token,
            getattr(response_model, "__name__", str(response_model)),
            in_prompt,
            in_history,
        )
        return await original(self, response_model, user_content, *args, **kwargs)

    patch.setattr(ConversationFacilitator, "submit", wrapper)


def _wheels_by_layer(nexus) -> dict[int, list]:
    """Every wheel under the nexus, grouped by its cycle's perspective count."""
    grouped: dict[int, list] = {}
    for cycle, wheel in WheelRepository().find_by_nexus(nexus):
        grouped.setdefault(len(cycle.perspective_hashes), []).append(wheel)
    return grouped


async def _run_arm(label: str, climb: bool, monkeypatch) -> dict:
    """Run the SHIPPED pipeline with the climb off and on.

    `refine_from_coarser=False` is the Advisor path as it was: one wheel, the
    top-plausibility one. `True` is the policy the Advisor now passes
    (`EXPLORE_REFINE_FROM_COARSER`), so both arms measure code that runs in
    production rather than a hand-rolled stand-in for it — which matters here more
    than usual, since the thing being measured IS the wheel-selection policy, and a
    probe that picks its own wheels cannot be wrong about the one under test.
    """
    case = Case()
    case.commit()
    with scope(case.sid):
        hashes = await _perspectives(K)
        created = await CreateNexus().resolve(
            intent=INTENT, perspective_hashes=hashes
        )

        record = _Lookups()
        exposure = _Exposure()
        counter = _Counter()
        with monkeypatch.context() as patch:
            _count_calls(patch, counter)
            _watch_parent_lookups(patch, record)
            _watch_exposure(patch, exposure)
            started = time.monotonic()
            result = await ExplorationPipeline(
                nexus_hash=created.nexus.hash,
                max_deep_wheels=1,
                refine_from_coarser=climb,
            ).resolve()
            wall = time.monotonic() - started

        by_layer = _wheels_by_layer(created.nexus)
        # The pipeline degrades softly — a build that fails lands in `errors` and
        # comes back as an empty result, which downstream reads as "no wheels at this
        # k" instead of "the run broke". Say which it was.
        assert by_layer, (
            f"{label}: no wheels under the nexus. Pipeline said:"
            f" {result.errors or '(no errors reported)'}"
        )
        top = max(by_layer)
        # Rung by rung, in the order the pipeline ran them, resolved back to wheels
        # so the edge counts below are the real ones. `refinement_rungs` is a list of
        # rungs, so its INDEX is the running order and its contents the concurrency.
        wheels_by_hash = {
            w.hash: (layer, w)
            for layer, ws in by_layer.items()
            for w in ws
            if w.hash
        }
        deepened: list[dict] = []
        for rung in result.refinement_rungs:
            for wheel_hash in rung:
                found = wheels_by_hash.get(wheel_hash)
                if found is None:
                    continue
                layer, wheel = found
                deepened.append({
                    "layer": layer,
                    "wheel": wheel.short_hash,
                    "edges": len(wheel.edges),
                    "transformations": len(wheel.transformations),
                })

    return {
        "label": label,
        "wheel_counts": {layer: len(ws) for layer, ws in sorted(by_layer.items())},
        "top": top,
        "rungs": result.refinement_rungs,
        "deepened": deepened,
        "record": record,
        "exposure": exposure,
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
                f" `build_coarser_context` returned None every time, so the"
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

    # What each call in a tetrad could actually SEE. Measured, not read off the
    # signatures: this probe's first run reported "only Ac- is refined" from the
    # signatures alone, which is true of the PARAMETER and false of the context
    # window — the four calls share one conversation, so the block stays in history.
    print(
        "\n  WHAT EACH CALL IN ONE TETRAD ACTUALLY SAW"
        " (climb arm, one edge's conversation, in call order)"
    )
    conversations = climb["exposure"].with_marker()
    if not conversations:
        print("       the context never appeared in any prompt — nothing to show")
    else:
        # The LONGEST, not the first. Since Ac+ started being asked, most carrying
        # conversations are `ActionExtraction`'s isolated one-row ones, and picking
        # the first showed a single Ac+ line under a heading promising a tetrad.
        rows = max(conversations, key=len)
        print(f"       {'response model':<26}{'in its prompt':>14}{'in history':>12}")
        for model, in_prompt, in_history in rows:
            print(
                f"       {model:<26}{'YES' if in_prompt else 'no':>14}"
                f"{'YES' if in_history else 'no':>12}"
            )
        print(
            f"       ({len(conversations)} of"
            f" {len(climb['exposure'].by_conversation)} conversations in the run"
            f" carried it; the rest are other concerns' own facilitators)"
        )

    # And the same question asked ACROSS the run rather than within one tetrad,
    # because Ac+ cannot appear in the table above at all: `ActionExtraction` has its
    # own facilitator and `isolate()`s every candidate, so each Ac+ call is a
    # conversation of ONE row. Whether the position that the refinement recursion
    # exists for is being asked to refine is only visible here.
    print("\n  BY POSITION, ACROSS THE WHOLE CLIMB ARM")
    per_model: dict[str, list[int]] = {}
    for rows in climb["exposure"].by_conversation.values():
        for model, in_prompt, in_history in rows:
            tally = per_model.setdefault(model, [0, 0, 0])
            tally[0] += 1
            tally[1] += 1 if in_prompt else 0
            tally[2] += 1 if in_history and not in_prompt else 0
    print(f"       {'response model':<26}{'calls':>7}{'asked':>7}{'history only':>14}")
    for model in sorted(per_model):
        calls, asked, history_only = per_model[model]
        print(f"       {model:<26}{calls:>7}{asked:>7}{history_only:>14}")

    print("\n  WHICH CALLS ARE HANDED IT AS A PARAMETER")
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
    # Only the CLIMB half is asserted. The direct arm finding 0 parents is what
    # `refine_from_coarser=False` MEANS, and it is still the headless default — but
    # it is a baseline, not a promise, so pinning it would make a later decision to
    # climb by default fail here for being an improvement. The climb half is the
    # opposite: it is the shipped Advisor policy, and if it stops finding parents
    # that are sitting in the graph the recursion is silently off again with every
    # test still green.
    assert climb_hits, (
        "the climb found no parents, so the Advisor's deepest wheel is once again"
        " being generated with no coarser context — either the rungs are no longer"
        " ordered coarsest-first, or the chain they descend is no longer nested"
    )
    assert max(r["parents"] for r in climb_hits) > 1 or K < 3, (
        "no edge saw more than one parent at k >= 3, so the RECURSION (layer 1 up to"
        " L-1, chained transitively) has collapsed to a single-layer lookup"
    )

    # Every GENERATIVE position must be ASKED, in its own prompt. In history is a
    # weaker claim and it is the one this probe used to settle for: until 2026-09-11
    # Re+/Re- read `<broader_journey>` out of the conversation Ac- had filled, which
    # is refinement by accident of ordering — nothing enforced that Ac- ran first,
    # and an `isolate()` on any later call would have dropped it with every
    # signature untouched. Ac+ was worse than unasked: its own facilitator, its own
    # `isolate()`, Phase 1 before any parent lookup existed, and its candidate copied
    # into the tetrad verbatim, so the tetrad's LEADING position refined nothing.
    #: response model -> (calls, of which carried the section in their own prompt)
    asked: dict[str, tuple[int, int]] = {}
    for rows in climb["exposure"].by_conversation.values():
        for model, in_prompt, in_history in rows:
            calls, in_prompt_count = asked.get(model, (0, 0))
            asked[model] = (calls + 1, in_prompt_count + (1 if in_prompt else 0))
    # NOT "every call carries it": the coarsest rung has no ancestry, and a layer-1
    # wheel's Ac+ prompt is CORRECTLY bare — `coarser_journey_section` returns ""
    # rather than a "no parents" note, so the model is not invited to treat a
    # complete answer as a gap. So the claim is the RATIO, against the lookups that
    # actually found something: a position must be asked on exactly the edges that
    # have ancestry, and on all of them. Measured at k=2 as 4 of 6 lookups finding a
    # parent, and 12 of 18 Ac+ prompts / 4 of 6 tetrad prompts carrying the section
    # — the same fraction three times, which is the part that would break if any one
    # position were dropped or if the hand-off leaked between phases.
    for model in ("ActionCandidateDto", "AcMinusCompletionDto", "ReSideCompletionDto"):
        calls, in_prompt_count = asked.get(model, (0, 0))
        assert calls, (
            f"{model} was never submitted in the climb arm, so this probe cannot say"
            f" whether that position is refined — the arm no longer reaches it"
        )
        assert in_prompt_count * len(climb["record"].rows) == calls * len(climb_hits), (
            f"{model} was asked to refine in {in_prompt_count} of {calls} prompts,"
            f" but {len(climb_hits)} of {len(climb['record'].rows)} edges have"
            f" ancestry to refine from. That position is not being asked on the edges"
            f" that have a broader path — at best it is reading the hierarchy out of"
            f" a conversation someone else filled, which is what the 2026-09-11 fix"
            f" removed the reliance on"
        )
    # HS scoring and the category reframings are deliberately NOT asked. Transition
    # HS is rendered as evidence and does NOT gate (`HS_THRESHOLD` is polarity-level
    # only), but biasing a judgement with "be more concrete than the
    # broader path" is a different class of defect from an unrefined statement; the
    # reframings derive from positions that are already refined. They still have the
    # hierarchy in their window, because they share the tetrad's facilitator — which
    # is exactly why this has to be asserted on the PROMPT and not on visibility.
    for model in ("HsScoringDto", "CategoryReframingDto"):
        calls, in_prompt_count = asked.get(model, (0, 0))
        assert in_prompt_count == 0, (
            f"{model} was handed a refinement instruction in {in_prompt_count} of"
            f" {calls} prompts. That is a reasoning change, not a wiring one: read"
            f" TestScoringIsDeliberatelyNotRefined in tests/test_refinement_context.py"
            f" before deciding it is an improvement"
        )
    print(
        f"\n  direct: {len(direct_hits)} of {len(direct['record'].rows)} lookups"
        f" found a parent."
        f"\n  climb:  {len(climb_hits)} of {len(climb['record'].rows)} lookups"
        f" found a parent."
    )
