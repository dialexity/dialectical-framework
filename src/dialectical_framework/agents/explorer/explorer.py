"""
Explorer: Conversational agent for dialectical exploration.

Scoped to a Case + Nexus (sid + nexus_hash). Helps users navigate
transformations and understand the synthetic wisdom (Ac+, Re+, S+).

Also contains ExplorationPipeline — the headless pipeline for programmatic use.
"""

from __future__ import annotations

import asyncio
from contextlib import aclosing
from typing import TYPE_CHECKING, AsyncGenerator, Optional

from pydantic import BaseModel, Field

from dialectical_framework.agents.agent_context import agent_scope
from dialectical_framework.graph.scope_context import require_current_sid
from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.agents.explorer.system_prompts import system_prompt
from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.agents.app_spec import AppSpec, resolve_app_layer
from dialectical_framework.agents.stream_events import StreamEvent
from dialectical_framework.agents.toolsets import merge_app_tools
from dialectical_framework.graph.rendering import pathway_line
from dialectical_framework.graph.repositories.nexus_repository import \
    NexusRepository
from dialectical_framework.utils.progress import (progress_hash_key,
                                                  progress_scope)

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Conversational Agent
# ---------------------------------------------------------------------------


class ChatResponse(BaseModel):
    """Response from the explorer chat."""

    message: str = Field(description="The assistant's response message")


class Explorer:
    """
    Conversational agent for dialectical exploration.

    Scoped to a Nexus within a Case. The host app is responsible for:
    - Managing scope(sid)
    - Persisting and loading conversation messages
    - Wrapping chat() calls in `with scope(sid):`

    Usage:
        with scope(case.sid):
            explorer = Explorer(nexus_hash="abc1234", app_preamble="...")
            response = await explorer.chat("What pathways do I have?")

        # Resuming with history:
        with scope(case.sid):
            explorer = Explorer(nexus_hash="abc1234", messages=loaded_messages)
            response = await explorer.chat("Tell me about the Ac+ path")
    """

    AGENT_NAME = "explorer"

    def __init__(
        self,
        nexus_hash: str,
        app_preamble: Optional[str] = None,
        messages: Optional[list] = None,
        app_tools: Optional[list] = None,
        app: Optional[AppSpec] = None,
    ) -> None:
        self._nexus_hash = nexus_hash
        # app: declarative app definition (Navigator base + voicing +
        # tool_guide + tools) — see AppSpec. Pass the SAME AppSpec to every
        # head (Analyst, Explorer, Advisor): the Explorer<->Advisor toggle
        # shares literal history (a missing tool breaks capability
        # mid-conversation), and the Analyst thread owes the user the same
        # domain resources by parity. For advanced-mode preambles compose
        # manually: app_preamble=my_app.navigator_preamble(advanced=True).
        app_preamble, app_tools = resolve_app_layer(
            app, app_preamble, app_tools, preamble_for="navigator"
        )
        self._tools = merge_app_tools(_build_tools(), app_tools)
        self._conversation = ConversationFacilitator(tools=self._tools)

        if messages:
            self._conversation._messages = list(messages)
        nexus_intent = self._resolve_nexus_intent()
        self._conversation.set_system_prompt(
            self._build_system_prompt(nexus_hash, nexus_intent, app_preamble)
        )

    def _resolve_nexus_intent(self) -> str:
        repo = NexusRepository()
        nexus = repo.find_by_hash_prefix(self._nexus_hash)
        if nexus is None:
            raise ValueError(f"Nexus not found: {self._nexus_hash}")
        return nexus.intent or "(no intent specified)"

    def _build_system_prompt(
        self, nexus_hash: str, nexus_intent: str, app_preamble: Optional[str] = None
    ) -> str:
        parts = []
        if app_preamble:
            parts.append(app_preamble)
        parts.append(system_prompt(nexus_hash=nexus_hash, nexus_intent=nexus_intent))
        return "\n\n".join(parts)

    async def chat(self, user_message: str) -> str:
        require_current_sid()  # unscoped turns silently drop all work
        with agent_scope(self.AGENT_NAME):
            result = await self._conversation.submit(ChatResponse, user_message)
            return result.message

    async def chat_stream(self, user_message: str) -> AsyncGenerator[StreamEvent, None]:
        """Stream one turn's events. **The caller owes this generator a CLOSE** —
        see `Advisor.chat_stream`, which carries the whole argument; a bare
        `async for` with a `break` defers the provider connection to the collector.
        """
        require_current_sid()  # unscoped turns silently drop all work
        with agent_scope(self.AGENT_NAME):
            # `aclosing` for the reason spelled out in `Advisor.chat_stream`: only a
            # close runs `submit_stream`'s cleanup on the abandoned exit, and this
            # link fires only once the caller closes THIS generator.
            async with aclosing(
                self._conversation.submit_stream(ChatResponse, user_message)
            ) as rounds:
                async for event in rounds:
                    yield event

    @property
    def messages(self) -> list:
        return self._conversation._messages

    @property
    def nexus_hash(self) -> str:
        return self._nexus_hash


def _build_tools() -> list:
    from dialectical_framework.agents.explorer.skills.build_wheels import \
        build_wheels
    from dialectical_framework.agents.explorer.skills.explore_transformations import \
        explore_transformations
    from dialectical_framework.agents.explorer.tools.expand_nexus import \
        expand_nexus
    from dialectical_framework.agents.explorer.tools.generate_synthesis import \
        generate_synthesis
    from dialectical_framework.agents.explorer.tools.present_exploration import \
        present_exploration
    from dialectical_framework.agents.orchestrator.tools.audit_feasibility import \
        audit_feasibility
    from dialectical_framework.agents.orchestrator.tools.create_dx_input import \
        create_dx_input
    from dialectical_framework.agents.orchestrator.tools.digest_input import \
        digest_input
    from dialectical_framework.agents.orchestrator.tools.get_schema import \
        get_schema
    from dialectical_framework.agents.orchestrator.tools.inspect_node import \
        inspect_node
    from dialectical_framework.agents.orchestrator.tools.query_graph import \
        query_graph
    from dialectical_framework.agents.orchestrator.tools.read_digest import \
        read_digest
    from dialectical_framework.agents.orchestrator.tools.read_input import \
        read_input

    return [
        build_wheels,
        explore_transformations,
        generate_synthesis,
        audit_feasibility,
        expand_nexus,
        create_dx_input,
        present_exploration,
        digest_input,
        read_digest,
        read_input,
        inspect_node,
        query_graph,
        get_schema,
    ]


# ---------------------------------------------------------------------------
# Headless Pipeline (for programmatic use)
# ---------------------------------------------------------------------------


class StepError(BaseModel):
    step: str
    message: str
    hash: Optional[str] = None


def _causality_probability(wheel) -> float:
    """Raw causality P for ranking, or -1.0 when the wheel has no estimation.

    Module level because two selections rank on it — which wheels get deepened, and
    which coarser wheel each of them refines from — and a wheel with no estimation
    has to lose both, not raise.
    """
    from dialectical_framework.graph.nodes.estimation import \
        CausalityProbabilityEstimation

    for est, _ in wheel.estimations.all():
        if isinstance(est, CausalityProbabilityEstimation):
            return est.value if est.value is not None else -1.0
    return -1.0


class ExplorationResult(BaseModel):
    nexus_hash: str
    cycle_hashes: list[str] = []
    wheel_hashes: list[str] = []
    # Wheels that got transformations this run (== wheel_hashes unless the
    # pipeline was capped via max_deep_wheels). Synthesis should follow these.
    deepened_wheel_hashes: list[str] = []
    transformation_count: int = 0
    #: Every transformation now ON the deepened wheels — newly generated AND
    #: reused. An `adopted_pathway` ground IS a Transformation hash, so a caller
    #: that reports only a count hands the model a pathway it cannot name; and a
    #: count of NEW ones reads as zero on the common idempotent case (a wheel
    #: sharing edge pairs with one already deepened reuses every transformation),
    #: which says "no pathway exists" about a wheel that is fully developed.
    transformation_hashes: list[str] = []
    #: The order the wheels were deepened in, grouped into layer rungs, coarsest
    #: first — the shape `refine_from_coarser` produces. One rung means no climb
    #: happened (either it was off, or the target is a 1-PP wheel with nothing
    #: coarser to refine from). Reported because "which wheels" does not say
    #: whether the refinement had anything to read: a rung deepened AFTER the
    #: wheel that should refine from it is a rung that arrived too late.
    refinement_rungs: list[list[str]] = []
    errors: list[StepError] = []
    reports: list = []

    model_config = {"arbitrary_types_allowed": True}


class ExplorationPipeline(ReasonableConcern[ExplorationResult]):
    """
    Headless exploration pipeline.

    Runs the full exploration within an existing Nexus:
    1. Build structural combinations (Cycles + Wheels)
    2. Generate Action-Reflection transformations for each Wheel

    `max_deep_wheels` caps step 2: ALL wheels are still built and estimated
    (structural, cheap), but only the top-plausibility wheels — deepest layer
    first, then highest causality P — get transformations. The rest stay
    shallow, available for deepening on demand.

    **None (the default) deepens EVERY wheel, and the wheel count is
    combinatorial**, so this default belongs to headless callers who have
    bounded their own input, not to anything a model can reach:

    - The Advisor passes `EXPLORE_DEEP_WHEELS = 1` (`advisor/tools/explore.py`).
    - The Explorer agent never runs this pipeline at all: its tools are
      `build_wheels` (structural, all wheels) and `explore_transformations` (one
      wheel the user picked), which is what "the user selects wheels" means here.
    - A headless caller bounds k instead — two perspectives, not two wheels.

    Priced with the LLM mocked (`tests/probe_explore_deep_wheels.py`): at k=2 the
    uncapped run asks for 100 formatted calls against the capped run's 36, and
    only 4 of the 100 build wheels — the rest is per-wheel deepening. Wheels
    sharing edge pairs reuse transformations, but that saves ~30%, not an order
    of magnitude. At k=4 (96 wheels) the uncapped run had not finished after 41
    minutes with a zero-latency model, so the ceiling is graph work before any
    provider time is added. Uncapped is a batch mode; pass a cap for anything a
    person is waiting on.

    `refine_from_coarser` decides whether the capped wheels are deepened ALONE or
    with their coarser ancestry underneath them, and that is the difference between
    the framework's refinement recursion running and not running at all.
    `TransformationGeneration` asks `find_parent_transformations` for the coarser
    Transformations its edge descends from and renders them into the prompt as the
    broader journey the current step has to be more concrete than. With the top
    wheel deepened alone on a fresh nexus that lookup has nothing to find —
    measured at k=4 in `tests/probe_transformation_recursion.py` as 0 of 8 lookups
    finding a parent, so the MOST detailed arrangement was generated with no
    refinement context at all, which is the one place the theory says it matters
    most. Deepening the ancestry first turns that into 18 of 20, chained
    transitively (a layer-4 edge sees layers 1, 2 and 3 at once). The edge count
    goes up 2.5x (20 against 8) but the WHOLE call only 1.5x — 273 provider calls
    against 177 at k=4, ~5% off-provider wall clock — because building and
    estimating all 96 wheels is paid either way. And they are ordered
    coarsest-first, so the smallest arrangement finishes first and the person reads
    it while the deeper rungs run.

    Does not create nexuses — that's the Analyst's job.
    Does not interact with the user — curates the graph and returns results.
    """

    def __init__(
        self,
        nexus_hash: str,
        perspective_hashes: Optional[list[str]] = None,
        max_deep_wheels: Optional[int] = None,
        refine_from_coarser: bool = False,
    ) -> None:
        self.nexus_hash = nexus_hash
        self.perspective_hashes = perspective_hashes or []
        self.max_deep_wheels = max_deep_wheels
        # Off by default so headless callers keep the behaviour they have. Worth
        # knowing before leaving it off: uncapped-and-off deepens every wheel in ONE
        # gather, which makes refinement a race — whether a layer-3 wheel finds its
        # layer-2 parents depends on which task happened to commit first. Layering
        # is what makes an uncapped run reproducible, so a batch caller that wants
        # the same transformations twice wants this on as well.
        self.refine_from_coarser = refine_from_coarser

    async def resolve(self) -> ExplorationResult:
        """Run the pipeline as ONE progress stream.

        The stage is `exploration` and the key is the nexus, which is the one node the
        person named to get here. Both are DISCARDED when a caller already owns a stream
        — the Advisor's `explore` opens one around this same pipeline — so the split
        below is what lets this be either an entry point or a sub-step: the scope defers,
        and the steps `BuildWheels` and the two skills report fold into the caller's
        stream instead of opening a second one.

        Without this the two skills under `_explore_wheel` each closed a stream of their
        own, so one direct call published `2 x deepened wheels` `final` events and the
        whole wheel-building phase in front of them published none.
        """
        with progress_scope("exploration", key=progress_hash_key(self.nexus_hash)):
            return await self._resolve()

    async def _resolve(self) -> ExplorationResult:
        from dialectical_framework.agents.explorer.skills.build_wheels import \
            BuildWheels
        from dialectical_framework.agents.explorer.skills.explore_transformations import \
            ExploreTransformations

        errors: list[StepError] = []
        reports: list = []

        cycle_hashes: list[str] = []
        wheel_hashes: list[str] = []

        try:
            build = BuildWheels(
                nexus_hash=self.nexus_hash,
                perspective_hashes=self.perspective_hashes,
            )
            build_result = await build.resolve()
            reports.append(build.report)

            cycle_hashes = [c.hash for c in build_result.new_cycles if c.hash]
            wheel_hashes = [w.hash for w in build_result.new_wheels if w.hash]
        except Exception as e:
            errors.append(StepError(step="build_wheels", message=str(e)))
            self._report.ok = False
            self._report.summary = f"Wheel building failed: {e}"
            return ExplorationResult(
                nexus_hash=self.nexus_hash,
                errors=errors,
                reports=reports,
            )

        if not wheel_hashes:
            self._report.ok = True
            self._report.summary = f"Built {len(cycle_hashes)} cycles, no new wheels"
            return ExplorationResult(
                nexus_hash=self.nexus_hash,
                cycle_hashes=cycle_hashes,
                errors=errors,
                reports=reports,
            )

        target_hashes = self._select_deep_wheels(build_result.new_wheels)
        plan = self._plan_rungs(target_hashes)
        rungs = [hashes for _, hashes in plan]
        # Flattened in the order they will actually be deepened, so a caller reading
        # `deepened_wheel_hashes` sees the chain, not the ranking.
        deep_wheel_hashes = [wh for rung in rungs for wh in rung]

        async def _explore_wheel(
            wheel_hash: str,
        ) -> tuple[list, Optional[StepError]]:
            try:
                explore_tr = ExploreTransformations(wheel_hash=wheel_hash)
                tr_result = await explore_tr.resolve()
                reports.append(explore_tr.report)
                # `.all`, not `.new`: the question the caller is answering is
                # "what pathways does this wheel now have", and a reused
                # transformation is as adoptable as a freshly generated one.
                return [t for t in tr_result.all if t.hash], None
            except Exception as e:
                return [], StepError(
                    step="explore_transformations",
                    message=str(e),
                    hash=wheel_hash,
                )

        # One rung at a time, concurrent WITHIN a rung. The barrier between rungs is
        # the whole point: a wheel refines from Transformations that have to be
        # committed before its own generation reads for them, so a coarser rung
        # running alongside a finer one is a coarser rung that may as well not exist.
        # With `refine_from_coarser` off there is exactly one rung, which is the
        # single gather this replaced.
        wheel_results: list = []
        for rung in rungs:
            wheel_results.extend(
                await asyncio.gather(*[_explore_wheel(wh) for wh in rung])
            )
        transformations: list = []
        for found, error in wheel_results:
            transformations.extend(found)
            if error:
                errors.append(error)
        # Deduped by hash: opposite-edge transformations are shared across wheels
        # sharing edge pairs, and one listed twice reads as two pathways. Sorted
        # for the same reason rendered structures are (deterministic ordering).
        by_hash = {t.hash: t for t in transformations}
        transformation_hashes = sorted(by_hash)
        transformation_count = len(transformation_hashes)

        # Set difference, not a subtraction of lengths: an ancestry rung can be a
        # wheel that ALREADY existed (a second explore on an expanded nexus builds
        # only the new arrangements), so it is deepened without being in
        # `wheel_hashes` — and the arithmetic would then under-report the shallow
        # ones, or go negative and report a wheel count that never existed.
        deepened_set = set(deep_wheel_hashes)
        shallow_count = sum(1 for wh in wheel_hashes if wh not in deepened_set)
        # Same rule as AnalysisPipeline: degrade, but never silently. Every
        # transformation failing is not "exploration complete" — and the
        # consequence lands squarely on the decision ceremony, since an adopted
        # pathway IS a transformation, so a wheel with none can only ground a
        # cost and never a recipe for living with it. `errors` used to ride home
        # on ExplorationResult, which no tool renders; `str(report)` is the whole
        # of what the model learns from a mutating call.
        # Zero transformations with no errors stays ok: that is "nothing new to
        # add", which is a real success.
        self._report.ok = bool(transformation_count) or not errors
        self._report.summary = (
            f"Exploration complete: {len(cycle_hashes)} cycles, "
            f"{len(wheel_hashes)} wheels, "
            f"{transformation_count} transformations"
            + (
                f" (deepened top {len(target_hashes)} wheel(s) by plausibility"
                + (
                    f" plus {len(deep_wheel_hashes) - len(target_hashes)} coarser "
                    f"wheel(s) they refine from"
                    if len(deep_wheel_hashes) > len(target_hashes)
                    else ""
                )
                + f"; {shallow_count} built but not deepened)"
                if shallow_count
                else ""
            )
        )
        self._report.artifacts["nexus_hash"] = self.nexus_hash
        self._report.artifacts["cycle_hashes"] = cycle_hashes
        self._report.artifacts["wheel_hashes"] = wheel_hashes
        self._report.artifacts["deepened_wheel_hashes"] = deep_wheel_hashes
        # Only when a climb actually happened. A single rung is the same list again
        # under a second name, and the report is read by a model.
        if len(plan) > 1:
            self._report.artifacts["refinement_rungs"] = [
                f"{f'layer {layer}' if layer else 'layer unknown'}:"
                f" {', '.join(hashes)}"
                for layer, hashes in plan
            ]
        if errors:
            failed = "; ".join(f"{e.hash or '?'}: {e.message}" for e in errors)
            self._report.summary += (
                f" — {len(errors)} wheel(s) FAILED to deepen ({failed})"
            )
            self._report.artifacts["errors"] = [e.model_dump() for e in errors]
        self._report.artifacts["transformation_count"] = transformation_count
        # The count was never enough, and a bare hash list is not much better.
        # `adopted_pathway` asks for ONE Transformation as the person's ongoing
        # recipe; a caller handed "12 transformations" has nothing to pass, and
        # one handed 12 opaque hashes cannot tell which recipe it is adopting.
        # Measured as 0/6 records carrying an adopted pathway in
        # `claim2-weak-r10`, INCLUDING the cells that called `explore`
        # themselves — so this was never an election failure like `explore`
        # itself was; the ground was unnameable from the tool's own output.
        if transformation_hashes:
            pathways = [
                line
                for line in (
                    pathway_line(by_hash[h]) for h in transformation_hashes
                )
                if line
            ]
            if pathways:
                self._report.artifacts["pathways"] = pathways

        return ExplorationResult(
            nexus_hash=self.nexus_hash,
            cycle_hashes=cycle_hashes,
            wheel_hashes=wheel_hashes,
            deepened_wheel_hashes=deep_wheel_hashes,
            transformation_count=transformation_count,
            transformation_hashes=transformation_hashes,
            refinement_rungs=rungs,
            errors=errors,
            reports=reports,
        )

    def _select_deep_wheels(self, wheels: list) -> list[str]:
        """
        Pick which wheels get transformations this run.

        No cap → all of them. With a cap: rank by layer (perspective count,
        deepest first — richer causal chains) then by raw causality P within
        the layer (raw is comparable among siblings; normalization shares the
        denominator). Wheels without an estimation (e.g. 1-PP) rank last
        within their layer.
        """
        hashes = [w.hash for w in wheels if w.hash]
        if self.max_deep_wheels is None or self.max_deep_wheels >= len(hashes):
            return hashes
        if self.max_deep_wheels <= 0:
            return []

        def _layer(wheel) -> int:
            try:
                return wheel.polarity_count
            except ValueError:
                return 0

        ranked = sorted(
            (w for w in wheels if w.hash),
            key=lambda w: (_layer(w), _causality_probability(w)),
            reverse=True,
        )
        return [w.hash for w in ranked[: self.max_deep_wheels]]

    def _plan_rungs(self, target_hashes: list[str]) -> list[tuple[int, list[str]]]:
        """Group the wheels to deepen into layer rungs, coarsest first.

        `(layer, hashes)` per rung, in the order they must run. With
        `refine_from_coarser` off this is one rung holding the targets — the single
        gather the caller used to do. On, each target gains one coarser ancestor per
        layer below it, and everything is regrouped by layer so a target that is
        itself another target's ancestor cannot run alongside it.

        The chain is NESTED, because that is the only shape
        `find_parent_transformations` can walk: it enumerates `combinations` of the
        asking wheel's PPs and looks for coarser wheels whose PP set is a SUBSET, so
        a layer-2 wheel refines a layer-3 wheel only if its perspectives are among
        that wheel's. Picking the best wheel per layer independently would satisfy
        that for the top wheel (its PP set contains every coarser set in the nexus)
        and break it in the middle of the chain, which is where the transitive walk
        lives.

        Selection ranks the ancestor whose edges match the most of the finer wheel's
        LAST, by not ranking on it at all — that is what `_find_matching_parent_edge`
        will actually look for, and it is knowable only once the transformations
        exist, which is the thing this is choosing an order to build.
        """
        if not target_hashes:
            return []
        if not self.refine_from_coarser:
            return [(0, list(target_hashes))]

        from dialectical_framework.graph.repositories.wheel_repository import \
            WheelRepository

        nexus = NexusRepository().find_by_hash_prefix(self.nexus_hash)
        if nexus is None:
            return [(0, list(target_hashes))]

        # ONE query for every wheel under the nexus WITH its cycle, which is where
        # the perspective sets are. Reading `wheel.cycle` per wheel instead would be
        # a round-trip each, over a set that is combinatorial in k (96 wheels at
        # k=4). Pre-existing wheels have to be in here too: a second explore on an
        # expanded nexus builds only the new arrangements, and the coarser ones a
        # new wheel refines from are exactly the ones already there.
        pps_by_hash: dict[str, frozenset[str]] = {}
        wheels_by_hash: dict[str, object] = {}
        for cycle, wheel in WheelRepository().find_by_nexus(nexus):
            if wheel.hash:
                pps_by_hash[wheel.hash] = frozenset(cycle.perspective_hashes or [])
                wheels_by_hash[wheel.hash] = wheel

        prob_memo: dict[str, float] = {}

        def probability(wheel_hash: str) -> float:
            if wheel_hash not in prob_memo:
                prob_memo[wheel_hash] = _causality_probability(
                    wheels_by_hash[wheel_hash]
                )
            return prob_memo[wheel_hash]

        # Memoised on the perspective set, so a subset two targets share is descended
        # once. With that, the estimation reads are bounded by the wheels in the
        # nexus, which is the same order `_select_deep_wheels` already pays over the
        # wheels built this run.
        chain_memo: dict[frozenset[str], tuple[int, tuple, list[str]]] = {}

        def descend(current: frozenset[str]) -> tuple[int, tuple, list[str]]:
            """Best chain strictly inside `current`, coarsest-first.

            LENGTH FIRST, plausibility only to break ties — and that ordering is the
            whole reason this is a search and not a per-layer pick. A more plausible
            ancestor that no coarser wheel fits inside ends the climb one rung down;
            a less plausible one that reaches layer 1 gives the target parents at
            every layer below it, which is the transitive refinement this exists for.
            Depth is the thing being bought.
            """
            if current in chain_memo:
                return chain_memo[current]
            layer = len(current) - 1
            best: tuple[int, tuple, list[str]] = (0, (), [])
            if layer >= 1:
                candidates = sorted(
                    (
                        h
                        for h, other in pps_by_hash.items()
                        if len(other) == layer and other < current
                    ),
                    # Hash after P so two runs pick the same rung out of a tie.
                    key=lambda h: (-probability(h), h),
                )
                for h in candidates:
                    length, probs, chain = descend(pps_by_hash[h])
                    candidate = (length + 1, (probability(h),) + probs, chain + [h])
                    if candidate[:2] > best[:2]:
                        best = candidate
            chain_memo[current] = best
            return best

        by_layer: dict[int, set[str]] = {}
        unplaced: list[str] = []
        for target in target_hashes:
            pps = pps_by_hash.get(target)
            if not pps:
                # No perspective set to descend from — deepen it, but last, and
                # without claiming an ancestry it may not have.
                unplaced.append(target)
                continue
            by_layer.setdefault(len(pps), set()).add(target)
            _, _, chain = descend(pps)
            for wheel_hash in chain:
                by_layer.setdefault(len(pps_by_hash[wheel_hash]), set()).add(
                    wheel_hash
                )

        plan = [(layer, sorted(by_layer[layer])) for layer in sorted(by_layer)]
        if unplaced:
            plan.append((0, unplaced))
        return plan


# There is deliberately NO `@llm.tool` wrapper around this pipeline here.
#
# One used to live at the bottom of this file, uncapped, and it was in no
# toolset: `_build_tools()` above hands the Explorer `build_wheels` +
# `explore_transformations`, the system prompt tells it to let the user pick a
# wheel and deepen that one, and the Advisor has its own budgeted `explore`
# (`advisor/tools/explore.py`). Nothing imported it but a signature test that
# listed it among the framework's tools — so it read as live, and wiring it into
# `_build_tools()` would have handed the model a single call that deepens every wheel
# the combinatorics produced. Measured at k=4 (96 wheels), with the LLM MOCKED so
# no call takes any time at all, that call had not returned after 41 minutes
# (`tests/probe_explore_deep_wheels.py`).
#
# If an agent ever needs the whole pipeline in one call, it needs a cap in its
# signature, not a default of None.
