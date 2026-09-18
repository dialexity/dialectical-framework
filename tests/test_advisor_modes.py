"""
`Advisor(read_only=True)` — a head that counsels from the understanding and
cannot change it.

The contract is enforced in two places and nowhere else: the TOOLSET (no write
tool is built at all) and the closing seam (`_repair_unrecorded_decision`
declines, so the framework never writes a Decision on its own initiative here).
The prompt is told about it so the head does not spend turns reaching for what it
does not have — but the prompt is not what stops it, which is the same division
of labour as the nexus pin.

Three things in here are worth knowing before editing them.

`_WRITE_TOOL_NAMES` (the prompt's write set) and `_build_read_only_tools` (the
toolset) are two lists that must agree, and nothing but `TestTheTwoListsAreOne`
holds them together: a tool added to one and not the other gives a head that
holds a write tool while being told it has none, or the reverse.

The seam test asserts the classifier is never ASKED, not merely that nothing was
written — a repair that ran and then failed to write would look identical from
the outside, and it is not the same fact.

And `_settle_deferred_work` / `_refresh_context` deliberately still run: settling
honours one-writer-per-sid (a read-only head reading a half-woven graph is worse
than reading a shallow one) and the refresh is a read. `TestTheGateHasOneSite`
is what keeps a well-meaning "read-only means do nothing" edit from taking them.
"""

from __future__ import annotations

import inspect

from dialectical_framework.agents.advisor.advisor import (Advisor,
                                                          _build_read_only_tools)
from dialectical_framework.agents.advisor.system_prompts import (
    DEFAULT_TOOL_NAMES, _WRITE_TOOL_NAMES, system_prompt)
from dialectical_framework.agents.advisor.tools.scoped import \
    build_scoped_tools
from dialectical_framework.concerns.decision_confirmation_check import (
    ConfirmationVerdictDto, DecisionConfirmationCheck)
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.nexus import Nexus
from dialectical_framework.graph.scope_context import scope

# The DB-free repair stub, imported rather than re-declared: it binds the REAL
# seam methods, and a second copy would drift from the one every other seam test
# drives (`tests/` is on sys.path — see CLAUDE.md, Testing).
from test_decision_confirmation_repair import _StubAdvisor

READING_TOOLS = {"sync", "inspect_node", "read_digest"}


def _names(tools: list) -> set[str]:
    return {t.__name__ for t in tools}


def _tool_by_name(tools: list, name: str):
    return next(t for t in tools if t.__name__ == name)


def _new_nexus() -> Nexus:
    """A committed nexus in a fresh scope, for the pinned factory."""
    nexus = Nexus(intent="read-only counsel test")
    nexus.save()
    nexus.commit()
    return nexus


class TestTheToolsetOnlyReads:
    """What the head is handed, which is the whole enforcement."""

    async def test_the_unscoped_head_holds_the_three_reading_tools(self):
        advisor = Advisor(read_only=True)
        assert _names(advisor._tools) == READING_TOOLS

    async def test_no_write_tool_is_built(self):
        advisor = Advisor(read_only=True)
        assert not _names(advisor._tools) & _WRITE_TOOL_NAMES

    async def test_the_factory_alone_says_the_same(self):
        """Called directly, so a future `__init__` branch cannot be the only
        thing keeping the surface read-only."""
        assert _names(_build_read_only_tools()) == READING_TOOLS

    async def test_the_scoped_head_keeps_the_pin(self):
        """Read-only and counsel mode compose — the pinned `sync`, not the
        unscoped one.

        The discriminator is the SIGNATURE, not the name: both are called
        `sync`, and only the unscoped one exposes `nexus_hash` for the model to
        redirect. Asserting on the name would pass with the pin gone.
        """
        case = Case()
        case.commit()
        with scope(case.sid):
            tools = build_scoped_tools(_new_nexus().hash[:7], read_only=True)

        assert _names(tools) == READING_TOOLS
        sync = _tool_by_name(tools, "sync")
        assert list(inspect.signature(sync).parameters) == [], (
            "the read-only scoped head got the UNSCOPED sync — it can be "
            "pointed at any exploration in the case"
        )

    async def test_app_tools_are_still_merged(self):
        """Deliberate, and documented at the flag: the framework cannot tell a
        host's chart lookup from a host's write, so `read_only` governs the
        framework's own surface and the host owns its own. Refusing app tools
        here would push those apps onto `app_preamble=`, which silently unwires
        `app_tools` — the trap `advanced` fell into."""
        from mirascope import llm

        @llm.tool
        async def lookup_natal_chart(person: str) -> str:
            """Look up the natal chart for a person."""
            return f"chart for {person}"

        advisor = Advisor(read_only=True, app_tools=[lookup_natal_chart])
        assert _names(advisor._tools) == READING_TOOLS | {"lookup_natal_chart"}


class TestTheTwoListsAreOne:
    """The toolset and the prompt's write set are halves of one list.

    `system_prompt` derives the read-only render from `_WRITE_TOOL_NAMES` while
    `_build_read_only_tools` decides what is actually handed over, and nothing
    else compares them. Drift in either direction is silent and bad in a
    different way: a write tool missing from the set gives a head holding it and
    a prompt saying it has none; a read tool wrongly in the set makes the full
    Advisor's own prompt render as read-only.
    """

    def test_the_default_toolset_splits_exactly_into_reads_and_writes(self):
        assert set(DEFAULT_TOOL_NAMES) == READING_TOOLS | _WRITE_TOOL_NAMES

    def test_the_reading_half_is_what_the_read_only_head_gets(self):
        assert set(DEFAULT_TOOL_NAMES) - _names(_build_read_only_tools()) == (
            _WRITE_TOOL_NAMES
        )

    def test_audit_feasibility_counts_as_a_write(self):
        """It reads like a read and is not: a FeasibilityEstimation plus a
        critique Rationale, two provider calls per pathway. Pinned by name
        because it is the one members of this set a reader would move out of
        it."""
        assert "audit_feasibility" in _WRITE_TOOL_NAMES
        assert "audit_feasibility" not in _names(_build_read_only_tools())

    def test_discard_counts_as_a_write(self):
        """A write with the softest possible name — a soft-marked node is out of
        every active query afterwards."""
        assert "discard" in _WRITE_TOOL_NAMES
        assert "discard" not in _names(_build_read_only_tools())


class TestThePromptFollowsTheToolset:
    """Rendered from the tool NAMES, so the prompt cannot disagree with the
    tools the head holds — there is no second parameter to get out of step."""

    def _read_only_render(self) -> str:
        return system_prompt(tool_names=sorted(READING_TOOLS))

    def test_the_mandate_renders(self):
        assert "## What Is Not Available Here" in self._read_only_render()

    def test_the_mandate_is_absent_from_the_full_render(self):
        assert "## What Is Not Available Here" not in system_prompt()

    def test_one_write_name_is_enough_to_turn_it_off(self):
        """Derived from the names rather than passed as a flag: a scoped session
        wiring a single write tool is not a read-only surface."""
        render = system_prompt(tool_names=sorted(READING_TOOLS | {"anchor"}))
        assert "## What Is Not Available Here" not in render

    def test_an_unknown_app_tool_name_does_not_make_it_writable(self):
        """App tools are never in the write set — a host's own lookup must not
        turn the framework's read-only render off."""
        render = system_prompt(
            tool_names=sorted(READING_TOOLS | {"lookup_natal_chart"})
        )
        assert "## What Is Not Available Here" in render

    def test_the_building_arc_is_dropped(self):
        """Same reason it is dropped when scoped: the arc IS the building
        sequence, and there is nothing here to build with."""
        assert "## Default Arc" not in self._read_only_render()
        assert "## Default Arc" in system_prompt()

    def test_the_convergence_engine_is_dropped(self):
        assert "Decision Readiness" not in self._read_only_render()
        assert "Decision Readiness" in system_prompt()

    def test_the_sections_that_instruct_absent_tools_are_reworded(self):
        """The gap this feature is really about: gating the toolset does NOT
        gate the prompt. These three phrases each name a tool the head does not
        have, in a section that renders regardless of the toolset."""
        render = self._read_only_render()
        assert "After explore" not in render
        assert "anchor or ingest" not in render
        assert "announce additions and removals" not in render
        assert "silently `discard`" not in render

    def test_the_cache_seam_survives(self):
        """One breakpoint sentinel and the context slot LAST — the invariant
        `split_system_for_cache` rests on, asserted here because a new section
        appended after `_CONTEXT_SLOT` would break caching silently."""
        render = self._read_only_render()
        assert render.count("\n\n## Current Understanding\n\n") == 1
        assert render.rstrip().endswith("{dialectical_context}")


class TestTheClosingSeamDeclines:
    """The framework's own initiative, which is the half no toolset can gate.

    `_repair_unrecorded_decision` writes a Decision the model never recorded and
    schedules the weave that builds perspectives, cycles and wheels off the turn.
    On a read-only head it does not run at all.
    """

    def _confirming_classifier(self, monkeypatch, calls: list) -> None:
        async def fake_check(self, *, user_message, assistant_message):
            calls.append(user_message)
            return ConfirmationVerdictDto(
                confirmed=True,
                question="Buy out the cofounder or restructure?",
                stance="Buy him out",
                rationale="He is checked out.",
            )

        monkeypatch.setattr(DecisionConfirmationCheck, "resolve", fake_check)

    async def test_the_classifier_is_never_asked(self, monkeypatch):
        """Not "nothing was written" — nothing was CONCLUDED. A seam that ran
        and then failed to write looks the same from outside and is a different
        fact (and would cost a provider call on a surface whose contract is that
        it does nothing)."""
        calls: list = []
        self._confirming_classifier(monkeypatch, calls)

        advisor = _StubAdvisor([], principal="human", read_only=True)
        await advisor._repair_unrecorded_decision(
            "Write that down as the decision.", "**Your Decision** Buy him out..."
        )

        assert calls == []

    async def test_the_same_turn_repairs_on_a_writing_head(self, monkeypatch):
        """The control. Without it the test above passes on a stub that simply
        never reaches the classifier for some unrelated reason."""
        calls: list = []
        self._confirming_classifier(monkeypatch, calls)

        recorded: dict = {}
        from dialectical_framework.concerns.record_decision import RecordDecision

        async def fake_record(self, **kwargs):
            recorded.update(kwargs)
            return "abc1234deadbeef"

        monkeypatch.setattr(RecordDecision, "resolve", fake_record)

        advisor = _StubAdvisor([], principal="human", read_only=False)
        await advisor._repair_unrecorded_decision(
            "Write that down as the decision.", "**Your Decision** Buy him out..."
        )

        assert len(calls) == 1
        assert recorded["stance"] == "Buy him out"

    async def test_both_outcome_fields_stay_none(self, monkeypatch):
        """`None` is already documented on `ClosingOutcome` as "the seam did not
        run", and a read-only turn is a third way into it. It must not read as
        `NO_CLOSING`: the classifier never looked, so nothing was concluded
        about whether the person was closing."""
        self._confirming_classifier(monkeypatch, [])

        advisor = _StubAdvisor([], principal="human", read_only=True)
        advisor._last_closing = "stale"
        advisor._last_deferral = "stale"
        await advisor._repair_unrecorded_decision("write it down", "done")

        assert advisor._last_closing is None
        assert advisor._last_deferral is None

    async def test_a_model_recorded_decision_is_not_grounded_either(
        self, monkeypatch
    ):
        """The seam's OTHER branch. It fires when the model called
        `record_decision` itself, and it too weaves and grounds — so gating only
        the repair branch would leave the framework writing on a read-only head
        whenever a host wired a write tool of its own."""
        weaves: list = []

        async def fake_ensure(self):
            weaves.append(True)
            return []

        # Patched on the STUB, not on `Advisor`: the stub binds the real methods
        # as class attributes at class-creation time, so a patch on `Advisor`
        # would leave the bound copy in place and the test would pass vacuously.
        monkeypatch.setattr(
            _StubAdvisor, "_ensure_pathways_before_closing", fake_ensure
        )

        from dialectical_framework.agents.execution_report import \
            ExecutionReport
        from dialectical_framework.agents.stream_events import ToolResult

        advisor = _StubAdvisor(
            [
                ToolResult(
                    tool_name="record_decision",
                    report=ExecutionReport(tool="record_decision", ok=True),
                    raw_output="{}",
                )
            ],
            read_only=True,
        )
        await advisor._repair_unrecorded_decision("done", "recorded")

        assert weaves == []
        assert advisor._last_closing is None


class TestTheGateHasOneSite:
    """`self._read_only` is read in exactly one method, and that is the design.

    `_settle_deferred_work` must still run (one writer per sid — a read-only head
    that reads a half-woven graph is worse than one that reads a shallow one) and
    `_refresh_context` must still run (it is a read; a turn that must see the
    graph cannot be configured into not looking). A future "read-only means do
    nothing" edit would take both, and nothing else in the suite would notice.
    """

    def test_only_the_constructor_and_the_seam_read_the_flag(self):
        readers = {
            name
            for name, fn in vars(Advisor).items()
            if inspect.isfunction(fn) and "self._read_only" in inspect.getsource(fn)
        }
        assert readers == {"__init__", "_repair_unrecorded_decision"}, (
            "a new read of `self._read_only` — if it is a turn-loop gate, "
            "`_settle_deferred_work` and `_refresh_context` are exactly what "
            "must NOT be behind it; see this class's docstring"
        )
