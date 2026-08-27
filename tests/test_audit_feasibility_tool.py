"""Feasibility is asked for, not always computed.

WHY THESE TESTS
===============
`TransformationAudit` is off by default (it was 40% of `explore`'s provider spend
for an annotation nothing read — see `test_transformation_audit_optional.py`).
`audit_feasibility` is how a conversation gets it back: two calls, spent on the
pathway someone just asked about. Everything that makes that trade honest is
here:

1. **Already-assessed pathways cost nothing.** Without the skip, asking twice
   pays twice and leaves two critique Rationales whose prose disagrees, with
   nothing to say which one produced the surviving score.
2. **The reasoning travels, not just the number.** A band with no factors behind
   it is not an answer to "could I actually do that?", and the critique Rationale
   this reads had no reader anywhere in the framework before this tool.
3. **Nothing is dropped silently.** Bad hashes are named, over-cap targets are
   named as deferred, a failed audit is named — a shortened answer would
   otherwise read as "these are the feasible ones".
4. **One failure doesn't take the others.** The tool exists to answer about a
   specific pathway; losing the answers about the rest to one bad audit is the
   failure mode that matters.
5. **The pin holds.** It writes to the graph and spends provider calls, so in a
   scoped session it is guarded like the other write tools, not waved through
   like `inspect_node`.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.llm


# --- Fakes ----------------------------------------------------------------
#
# Subclasses of the REAL nodes, not stand-ins: the tool isinstance-checks
# `Transformation` (to tell a pathway hash from a wheel hash) and
# `FeasibilityEstimation` (to tell one estimation type from another), so a
# hand-rolled shape would take a different branch than production does. Only the
# relationship managers are shadowed, because those are what reach the DB.


class _Edge:
    """A Transformation's edge manager, empty — the edge label is decoration."""

    @staticmethod
    def get():
        return None


class _One:
    """A relationship manager holding exactly one target."""

    def __init__(self, target) -> None:
        self._target = target

    def get(self):
        return (self._target, object()) if self._target is not None else None

    def all(self):
        return [(self._target, object())] if self._target is not None else []


class _Many:
    def __init__(self, targets: list) -> None:
        self._targets = targets

    def all(self):
        return [(t, object()) for t in self._targets]


def _estimation(value: float, reasoning: str):
    from dialectical_framework.graph.nodes.estimation import \
        FeasibilityEstimation
    from dialectical_framework.graph.nodes.rationale import Rationale

    est = FeasibilityEstimation(value=value)
    object.__setattr__(est, "provider", _One(Rationale(text=reasoning)))
    return est


def _transition(instruction: str, band: tuple[float, str] | None = None):
    from dialectical_framework.graph.nodes.transition import Transition

    tr = Transition()
    object.__setattr__(tr, "instruction", instruction)
    object.__setattr__(
        tr, "estimations", _Many([_estimation(*band)] if band else [])
    )
    return tr


def _pathway(
    short: str,
    ac_plus: tuple[float, str] | None = None,
    re_plus: tuple[float, str] | None = None,
    ac_text: str = "Hand the accounts over deliberately",
    re_text: str = "Notice what the handover costs you",
):
    from dialectical_framework.graph.nodes.transformation import Transformation

    tr = Transformation()
    object.__setattr__(tr, "hash", f"{short}0000000000")
    object.__setattr__(tr, "edge", _Edge())
    object.__setattr__(tr, "ac_plus", _One(_transition(ac_text, ac_plus)))
    object.__setattr__(tr, "re_plus", _One(_transition(re_text, re_plus)))
    return tr


@pytest.fixture(autouse=True)
def cleanup_graph_db():
    """Override — every read here is stubbed at the repository."""
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    """Override — every read here is stubbed at the repository."""
    yield


@pytest.fixture
def wired(monkeypatch):
    """Wire the tool to a set of pathways, recording what got audited.

    The fake audit WRITES a band the way the real concern does, so the rendering
    assertions exercise the read-back path (score from the estimation, reasoning
    from its provider) rather than a return value the tool never looks at.
    """
    from dialectical_framework.agents.orchestrator.tools import \
        audit_feasibility as af_mod
    from dialectical_framework.concerns import transformation_audit as ta_mod
    from dialectical_framework.graph.repositories.node_repository import \
        NodeRepository

    state: dict = {"pathways": {}, "audited": [], "input_texts": [], "fail": set()}

    def fake_find(self, hash, node_type=None, **_kwargs):
        if hash in state["ambiguous"]:
            raise ValueError(f"Ambiguous hash '{hash}': matches 2 nodes.")
        return state["pathways"].get(hash)

    state["ambiguous"] = set()
    monkeypatch.setattr(NodeRepository, "find_by_hash", fake_find)

    async def fake_input_text():
        return "the situation as digested"

    monkeypatch.setattr(af_mod, "_get_input_text", fake_input_text)

    async def fake_audit(self, transformation, input_text="", audit_all=False):
        state["audited"].append(transformation.short_hash)
        state["input_texts"].append(input_text)
        if transformation.short_hash in state["fail"]:
            raise RuntimeError("provider said no")
        for manager, band in (
            (transformation.ac_plus, (0.7, "**Key Factors:** goodwill, timing")),
            (transformation.re_plus, (0.5, "**Key Factors:** habit, no slack")),
        ):
            result = manager.get()
            if result:
                object.__setattr__(result[0], "estimations", _Many([_estimation(*band)]))
        self._report.summary = "audited"
        return []

    monkeypatch.setattr(ta_mod.TransformationAudit, "resolve", fake_audit)
    return state


def _register(state, *pathways):
    for p in pathways:
        state["pathways"][p.short_hash] = p
    return [p.short_hash for p in pathways]


# --- Nothing is dropped silently -----------------------------------------


class TestBadInputCostsNothingAndSaysWhy:
    async def test_no_hashes_is_a_refusal_not_a_call(self, wired):
        from dialectical_framework.agents.orchestrator.tools.audit_feasibility import \
            run_audit_feasibility

        report = await run_audit_feasibility([])

        assert wired["audited"] == []
        assert '"ok": false' in report
        assert "hash" in report

    async def test_a_hash_that_is_not_a_pathway_is_named(self, wired):
        """The model usually has a longer prefix available — "the tool failed"
        does not tell it which of its hashes to fix."""
        from dialectical_framework.agents.orchestrator.tools.audit_feasibility import \
            run_audit_feasibility

        report = await run_audit_feasibility(["notapath"])

        assert wired["audited"] == []
        assert "notapath" in report
        assert "unresolved" in report

    async def test_ambiguous_prefix_is_reported_not_raised(self, wired):
        from dialectical_framework.agents.orchestrator.tools.audit_feasibility import \
            run_audit_feasibility

        good = _pathway("aaaaaaa")
        hashes = _register(wired, good)
        wired["ambiguous"].add("bb")

        report = await run_audit_feasibility(hashes + ["bb"])

        assert wired["audited"] == ["aaaaaaa"], (
            "one unusable hash must not cost the answer about a usable one"
        )
        assert "Ambiguous" in report

    async def test_brackets_and_duplicates_are_tolerated(self, wired):
        """`[[hash]]` is how pathways are rendered, so it is what comes back."""
        from dialectical_framework.agents.orchestrator.tools.audit_feasibility import \
            run_audit_feasibility

        p = _pathway("aaaaaaa")
        _register(wired, p)

        await run_audit_feasibility(["[[aaaaaaa]]", "aaaaaaa"])

        assert wired["audited"] == ["aaaaaaa"], "the same pathway twice is one audit"


# --- The trade the tool exists to make ------------------------------------


class TestAskingCostsTwoCallsAndAnswersWithReasons:
    async def test_an_unassessed_pathway_is_audited_and_rendered(self, wired):
        from dialectical_framework.agents.orchestrator.tools.audit_feasibility import \
            run_audit_feasibility

        hashes = _register(wired, _pathway("aaaaaaa"))
        report = await run_audit_feasibility(hashes)

        assert wired["audited"] == ["aaaaaaa"]
        assert "0.70" in report and "0.50" in report
        assert "goodwill, timing" in report, (
            "a band with no factors behind it does not answer 'could I do that?'"
        )
        assert "Ac+" in report and "Re+" in report

    async def test_the_situation_travels_into_the_audit(self, wired):
        """Feasibility is a judgement about the person's actual circumstances —
        resources, resistance, timelines. Without the input context it degrades
        into generic scoring that reads exactly the same."""
        from dialectical_framework.agents.orchestrator.tools.audit_feasibility import \
            run_audit_feasibility

        await run_audit_feasibility(_register(wired, _pathway("aaaaaaa")))

        assert wired["input_texts"] == ["the situation as digested"]

    async def test_already_assessed_pathways_cost_nothing(self, wired):
        from dialectical_framework.agents.orchestrator.tools.audit_feasibility import \
            run_audit_feasibility

        done = _pathway(
            "bbbbbbb",
            ac_plus=(0.8, "**Key Factors:** already on record"),
            re_plus=(0.4, "**Key Factors:** also on record"),
        )
        report = await run_audit_feasibility(_register(wired, done))

        assert wired["audited"] == []
        assert "already_estimated" in report
        assert "0.80" in report and "already on record" in report, (
            "the stored answer must be returned, not just the fact that one exists"
        )

    async def test_a_half_assessed_pathway_is_finished(self, wired):
        """Ac+ scored, Re+ not (a provider failure on the first pass). The
        missing half is exactly what someone is asking about, so it is worth the
        re-score of the half that already had one — the concern has no
        per-position entry point."""
        from dialectical_framework.agents.orchestrator.tools.audit_feasibility import \
            run_audit_feasibility

        half = _pathway("ccccccc", ac_plus=(0.8, "**Key Factors:** on record"))
        await run_audit_feasibility(_register(wired, half))

        assert wired["audited"] == ["ccccccc"]

    async def test_beyond_the_cap_is_deferred_and_named(self, wired):
        from dialectical_framework.agents.orchestrator.tools.audit_feasibility import (
            MAX_TRANSFORMATIONS_PER_CALL, run_audit_feasibility)

        pathways = [_pathway(f"{c * 7}") for c in "abcdefg"]
        report = await run_audit_feasibility(_register(wired, *pathways))

        assert len(wired["audited"]) == MAX_TRANSFORMATIONS_PER_CALL, (
            "an unbounded list lets one question re-spend the whole eager audit"
        )
        assert "deferred" in report
        for p in pathways[MAX_TRANSFORMATIONS_PER_CALL:]:
            assert p.short_hash in report, (
                "a silently truncated answer reads as 'these are the feasible ones'"
            )

    async def test_one_failing_audit_does_not_lose_the_others(self, wired):
        from dialectical_framework.agents.orchestrator.tools.audit_feasibility import \
            run_audit_feasibility

        first, second = _pathway("aaaaaaa"), _pathway("bbbbbbb")
        wired["fail"].add("aaaaaaa")

        report = await run_audit_feasibility(_register(wired, first, second))

        assert wired["audited"] == ["aaaaaaa", "bbbbbbb"]
        assert "audit_failed" in report and "aaaaaaa" in report
        assert "0.70" in report, "the pathway that did get assessed is still answered"

    async def test_an_unassessed_position_says_so_rather_than_scoring_zero(
        self, wired
    ):
        """A missing band is "not estimated", never "low" — the rule both agent
        prompts carry. The renderer must not be the thing that breaks it."""
        from dialectical_framework.agents.orchestrator.tools.audit_feasibility import \
            run_audit_feasibility

        wired["fail"].add("aaaaaaa")
        report = await run_audit_feasibility(_register(wired, _pathway("aaaaaaa")))

        assert "not estimated" in report
        assert "feasibility=0.00" not in report

    async def test_progress_counts_what_is_actually_audited(self, wired, monkeypatch):
        """Reused pathways cost nothing, so counting them would leave the bar
        short of its total for the rest of the run."""
        from dialectical_framework.agents.orchestrator.tools import \
            audit_feasibility as af_mod
        from dialectical_framework.utils import progress as progress_mod

        seen: list = []
        real_scope = progress_mod.progress_scope

        def spy(stage, **kwargs):
            ctx = real_scope(stage, **kwargs)

            class _Wrapper:
                def __enter__(self):
                    scope = ctx.__enter__()
                    seen.append(scope)
                    return scope

                def __exit__(self, *exc):
                    return ctx.__exit__(*exc)

            return _Wrapper()

        monkeypatch.setattr(progress_mod, "progress_scope", spy)
        fresh = _pathway("aaaaaaa")
        done = _pathway(
            "bbbbbbb", ac_plus=(0.8, "on record"), re_plus=(0.4, "on record")
        )
        await af_mod.run_audit_feasibility(_register(wired, fresh, done))

        assert len(seen) == 1
        assert seen[0].total == 1 == seen[0].done


# --- Wiring ---------------------------------------------------------------


class TestItIsReachableAndPinned:
    def test_both_agents_carry_it(self):
        from dialectical_framework.agents.advisor.advisor import \
            _build_tools as advisor_tools
        from dialectical_framework.agents.explorer.explorer import \
            _build_tools as explorer_tools

        assert "audit_feasibility" in {t.__name__ for t in advisor_tools()}
        assert "audit_feasibility" in {t.__name__ for t in explorer_tools()}

    def test_the_scoped_advisor_carries_a_guarded_one(self):
        from dialectical_framework.agents.advisor.tools.scoped import \
            build_scoped_tools

        assert "audit_feasibility" in {
            t.__name__ for t in build_scoped_tools("deadbeef")
        }

    async def test_a_pathway_from_another_exploration_is_refused(self, monkeypatch):
        """It writes to the graph and spends provider calls, so the pin applies
        — `inspect_node` is unguarded in scoped mode only because it reads."""
        from dialectical_framework.agents.advisor.tools import scoped as scoped_mod
        from dialectical_framework.graph.repositories.node_repository import \
            NodeRepository

        foreign = _pathway("fffffff")

        class _Nexus:
            _id = 1

        class _OtherNexus:
            _id = 2

        from dialectical_framework.graph.repositories.nexus_repository import \
            NexusRepository

        monkeypatch.setattr(
            NexusRepository, "find_by_hash_prefix", lambda self, h: _Nexus()
        )
        monkeypatch.setattr(
            NodeRepository, "find_by_hash", lambda self, h, **k: foreign
        )
        monkeypatch.setattr(
            "dialectical_framework.graph.rendering.find_nexus_for_transformation",
            lambda tr: _OtherNexus(),
        )

        refusal = scoped_mod._transformations_outside_scope_refusal(
            "deadbeef", ["fffffff"]
        )
        assert refusal is not None and "outside this exploration" in refusal

    async def test_a_pathway_of_the_pinned_exploration_is_allowed(self, monkeypatch):
        from dialectical_framework.agents.advisor.tools import scoped as scoped_mod
        from dialectical_framework.graph.repositories.nexus_repository import \
            NexusRepository
        from dialectical_framework.graph.repositories.node_repository import \
            NodeRepository

        mine = _pathway("aaaaaaa")

        class _Nexus:
            _id = 1

        monkeypatch.setattr(
            NexusRepository, "find_by_hash_prefix", lambda self, h: _Nexus()
        )
        monkeypatch.setattr(NodeRepository, "find_by_hash", lambda self, h, **k: mine)
        monkeypatch.setattr(
            "dialectical_framework.graph.rendering.find_nexus_for_transformation",
            lambda tr: _Nexus(),
        )

        assert (
            scoped_mod._transformations_outside_scope_refusal("deadbeef", ["aaaaaaa"])
            is None
        )

    def test_a_typo_is_not_a_scope_accusation(self, monkeypatch):
        """The tool reports unresolvable hashes with something usable; a guard
        that called them out-of-scope would send the model looking for a
        permission problem it doesn't have."""
        from dialectical_framework.agents.advisor.tools import scoped as scoped_mod
        from dialectical_framework.graph.repositories.nexus_repository import \
            NexusRepository
        from dialectical_framework.graph.repositories.node_repository import \
            NodeRepository

        class _Nexus:
            _id = 1

        monkeypatch.setattr(
            NexusRepository, "find_by_hash_prefix", lambda self, h: _Nexus()
        )
        monkeypatch.setattr(NodeRepository, "find_by_hash", lambda self, h, **k: None)

        assert (
            scoped_mod._transformations_outside_scope_refusal("deadbeef", ["nope"])
            is None
        )


class TestPromptWiring:
    def test_the_advisor_documents_when_to_spend_it(self):
        from dialectical_framework.agents.advisor.system_prompts import \
            SYSTEM_PROMPT

        p = " ".join(SYSTEM_PROMPT.split())
        assert "`audit_feasibility`" in p
        assert "two model calls per pathway" in p, "the price has to be visible"
        assert "not a step you run before offering anything" in p, (
            "routine pre-audit is the exact spend that was just removed"
        )

    def test_the_scoped_advisor_documents_it_too(self):
        from dialectical_framework.agents.advisor.system_prompts import \
            system_prompt

        p = " ".join(
            system_prompt(
                tool_names=["anchor", "sync", "explore", "deepen", "audit_feasibility"],
                scoped_nexus_hash="abc1234",
            ).split()
        )
        assert "`audit_feasibility`" in p

    def test_the_explorer_documents_it(self):
        from dialectical_framework.agents.explorer.system_prompts import \
            system_prompt

        p = " ".join(system_prompt(nexus_hash="abc1234", nexus_intent="whether to buy out").split())
        assert "`audit_feasibility`" in p
        assert "absent by design" in p
