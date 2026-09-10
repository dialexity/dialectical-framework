"""
Tests for the Advisor's deepen tool (on-demand wheel development).

`explore` deepens only the top-plausibility wheel (budget); `deepen` is the
follow-up when the person's lived reality picks a reading whose pathways
don't exist yet. One composed call: transformations then synthesis (always —
a deepened wheel without S+/S- is structurally unfinished), sequencing
absorbed in code.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.llm


@pytest.fixture
def stubs(monkeypatch):
    from dialectical_framework.agents.explorer.skills import \
        explore_transformations as et_mod
    from dialectical_framework.agents.explorer.skills import \
        generate_synthesis as gs_mod

    calls: dict = {"transformations": [], "synthesis": []}

    async def stub_transformations(self):
        calls["transformations"].append(self.wheel_hash)
        # The REAL result type, not a hand-rolled stand-in: a stub shaped by
        # hand only covers the fields the caller happened to read when it was
        # written, so it goes stale silently the moment the caller reads one
        # more (it did — `pathways` reads `.all`).
        return et_mod.ExploreTransformationsResult()

    async def stub_synthesis(self):
        calls["synthesis"].append(self.wheel_hash)
        return None

    monkeypatch.setattr(
        et_mod.ExploreTransformations, "resolve", stub_transformations
    )
    monkeypatch.setattr(gs_mod.GenerateSynthesis, "resolve", stub_synthesis)
    return calls


async def _deepen_collecting_progress(wheel_hash: str, sid: str = "sid-deepen") -> list:
    """Run `run_deepen` under a real bus and return the `ProgressEvent`s it published.

    Shared by the two progress tests below because both need the whole apparatus for
    the same reason: the things they assert — how many `final` events a call produces,
    and what `key` a host reads off them — exist only on the channel. Neither is
    visible from the scope object, and a fake publisher would let either test pass
    while the seam was broken.
    """
    import asyncio

    from dialectical_framework.agents.advisor.tools.deepen import run_deepen
    from dialectical_framework.events.graph_event_bus import GraphEventBus
    from dialectical_framework.graph.scope_context import scope
    from dialectical_framework.utils import progress as progress_module

    bus = GraphEventBus()
    await bus.connect()
    # RESTORE, never clear: the module-level bus is wired once by the session-scoped
    # container fixture, so `None` here would silently mute progress for every test
    # that ran afterwards.
    previous = progress_module._event_bus
    progress_module.set_event_bus(bus)

    received: list = []
    ready = asyncio.Event()

    async def _listen() -> None:
        async with bus.subscribe_progress(sid) as subscriber:
            ready.set()
            async for event in subscriber:
                received.append(event.message)

    listener = asyncio.create_task(_listen())
    await ready.wait()
    try:
        with scope(sid):
            await run_deepen(wheel_hash)
        # Publishes are fire-and-forget tasks; wait until the stream settles rather
        # than for a fixed interval, which drops the closing event under load and
        # reads as the very defect under test.
        previous_len = -1
        waited = 0.0
        while previous_len != len(received) and waited < 5.0:
            previous_len = len(received)
            await asyncio.sleep(0.05)
            waited += 0.05
    finally:
        listener.cancel()
        progress_module.set_event_bus(previous)
        await bus.disconnect()

    return received


class TestRunDeepen:
    async def test_generates_transformations_then_synthesis(self, stubs):
        from dialectical_framework.agents.advisor.tools.deepen import \
            run_deepen

        report = await run_deepen("wheel444")

        assert stubs["transformations"] == ["wheel444"]
        assert stubs["synthesis"] == ["wheel444"]
        assert "wheel444" in report

    async def test_synthesis_failure_is_soft_and_reported(
        self, monkeypatch, stubs
    ):
        """A wheel that can't synthesize (e.g. no transformations produced)
        still returns the transformation report, with the skip noted."""
        from dialectical_framework.agents.advisor.tools.deepen import \
            run_deepen
        from dialectical_framework.agents.explorer.skills import \
            generate_synthesis as gs_mod

        async def broken_synthesis(self):
            raise ValueError("no transformations yet")

        monkeypatch.setattr(
            gs_mod.GenerateSynthesis, "resolve", broken_synthesis
        )

        report = await run_deepen("wheel444")

        assert stubs["transformations"] == ["wheel444"]
        assert "synthesis_skipped" in report

    async def test_transformation_failure_propagates(self, monkeypatch):
        """Unlike synthesis, a transformations failure is the whole call
        failing — surface it to the tool layer (Mirascope turns raised
        exceptions into error tool-outputs)."""
        from dialectical_framework.agents.advisor.tools.deepen import \
            run_deepen
        from dialectical_framework.agents.explorer.skills import \
            explore_transformations as et_mod

        async def broken(self):
            raise ValueError("Wheel not found: wheel444")

        monkeypatch.setattr(et_mod.ExploreTransformations, "resolve", broken)

        with pytest.raises(ValueError, match="Wheel not found"):
            await run_deepen("wheel444")


class TestDeepenPromptWiring:
    def test_default_render_documents_deepen(self):
        from dialectical_framework.agents.advisor.system_prompts import \
            SYSTEM_PROMPT

        p = " ".join(SYSTEM_PROMPT.split())
        assert "`deepen`" in p
        # the decision point: lived reality over plausibility score
        assert "lived reality outranks the plausibility score" in p or (
            "reality outranks the plausibility score" in p
        )

    def test_scoped_render_documents_deepen_without_consent_ceremony(self):
        from dialectical_framework.agents.advisor.system_prompts import \
            system_prompt

        p = " ".join(
            system_prompt(
                tool_names=[
                    "anchor", "sync", "inspect_node", "read_digest",
                    "discard", "explore", "deepen",
                ],
                scoped_nexus_hash="abc1234",
            ).split()
        )
        assert "`deepen`" in p
        # deepening adds depth, doesn't change contents — no consent needed
        assert "never changes what the exploration contains" in p


class TestDeepenNamesThePathways:
    """A pathway the model cannot name is a pathway it cannot ground on.

    `adopted_pathway` takes a Transformation hash, and `claim2-weak-r10`
    recorded 0/6 decisions carrying one — including cells that explored
    themselves. The role was documented and the hash was never in reach.
    """

    async def test_pathways_are_listed_with_their_recipe(self, monkeypatch):
        from dialectical_framework.agents.advisor.tools.deepen import run_deepen
        from dialectical_framework.agents.explorer.skills import \
            explore_transformations as et_mod

        async def with_transformations(self):
            return et_mod.ExploreTransformationsResult(
                new=[_FakeTransformation("tr111", "Act on it")]
            )

        monkeypatch.setattr(
            et_mod.ExploreTransformations, "resolve", with_transformations
        )
        report = await run_deepen("wheel444")

        assert "tr111" in report
        assert "Act on it" in report, (
            "The hash alone is not a menu — the model has to tell one recipe "
            "from another to adopt one."
        )

    async def test_reused_pathways_are_listed_too(self, monkeypatch):
        """Deepening the same wheel twice returns everything as `existing`.

        Reading `.new` there reports no pathways for a wheel that has a full
        set of them — and the second call is the likely one, since `explore`
        already deepened the top wheel.
        """
        from dialectical_framework.agents.advisor.tools.deepen import run_deepen
        from dialectical_framework.agents.explorer.skills import \
            explore_transformations as et_mod

        async def only_existing(self):
            return et_mod.ExploreTransformationsResult(
                existing=[_FakeTransformation("tr222", "Keep at it")]
            )

        monkeypatch.setattr(
            et_mod.ExploreTransformations, "resolve", only_existing
        )
        report = await run_deepen("wheel444")

        assert "tr222" in report

    async def test_no_pathways_artifact_when_nothing_was_built(self, stubs):
        """An empty `pathways` list would read as "a menu with no options"
        rather than "this wheel has no recipes yet"."""
        from dialectical_framework.agents.advisor.tools.deepen import run_deepen

        report = await run_deepen("wheel444")

        assert "pathways" not in report


class TestOneDeepenIsOneProgressStream:
    """`deepen` is one action to a person and used to publish two closing events.

    Both skills it composes open a progress scope of their own, because both are
    reachable directly (`explore`, `explorer.py`, the `generate_synthesis` tool). Run
    in sequence that meant `final` for "transformation", then more events under
    "synthesis", then `final` again — so a host that clears its indicator on `final`
    cleared it halfway through and started over, which is exactly the "did it freeze
    or is it finished?" question the channel exists to answer.

    The fix is in the seam (`utils/progress.py`: a nested scope defers to the
    installed one) plus one scope here, so this asserts through `run_deepen` — a
    scope-object test cannot see the second `final`, and `test_progress.py` cannot
    see whether this tool installed anything.

    The stubs open scopes exactly where the real skills do. Their stage names and
    keys differ from the tool's on purpose: an inner name reaching the channel is
    the visible symptom of a scope that installed instead of deferring.

    **What this does NOT prove, stated so nobody reads more into a green run:** the
    scopes that defer here are the STUBS'. If `ExploreTransformations` or
    `GenerateSynthesis` dropped their own `progress_scope` tomorrow, this test would
    still pass — it pins that the TOOL installs a stream and that the SEAM folds a
    nested scope into it, at the two shapes the real skills use (`transformation`
    with `expect_progress` growth, `synthesis` with `total=`). That is deliberate:
    driving the real skills needs a committed Wheel with transitions and a full
    transformation run, and the thing worth catching cheaply is the tool's install
    plus the deferral. The real skills' scopes matter only where they are the
    OUTERMOST one — the `generate_synthesis` tool and `explore_transformations`'
    module-level helper — and THAT is pinned, since 2026-09-10, by
    `test_explore_progress_scope.py::TestTheTwoSkillsInstallTheirOwnScopes`, which runs
    both real skills against a real Wheel with nothing installed (~3s each under the
    mock brain, so the cost above was overestimated). **It has to be run that way, and
    that is the transferable part:** under an outer scope a skill whose own scope was
    deleted still publishes into the caller's stream, so a nested test notices the
    deletion only when the inner scope declared a `total` the outer denominator loses —
    deleting `GenerateSynthesis`' (`total=1`) fails a nested assertion at 13/12, and
    deleting `ExploreTransformations`' does not fail one at all.
    """

    @pytest.fixture
    def scoped_stubs(self, monkeypatch):
        from dialectical_framework.agents.explorer.skills import \
            explore_transformations as et_mod
        from dialectical_framework.agents.explorer.skills import \
            generate_synthesis as gs_mod
        from dialectical_framework.utils.progress import (expect_progress,
                                                          progress_scope,
                                                          report_progress)

        async def stub_transformations(self):
            # Declared inside the scope and not passed as `total`, because that is
            # what the real skill does — it opens at 0 and grows as each edge pair
            # discovers what it owes. So this covers BOTH ways a deferring skill can
            # size the bar: `expect_progress` here, `total=` in the synthesis stub.
            with progress_scope("transformation", key="whee"):
                expect_progress(2)
                report_progress("Working out what good looks like here")
                report_progress("Looking for concrete moves to take")
            return et_mod.ExploreTransformationsResult()

        async def stub_synthesis(self):
            with progress_scope("synthesis", key="whee", total=1):
                report_progress("Drawing out what emerges from the whole picture")
            return None

        monkeypatch.setattr(
            et_mod.ExploreTransformations, "resolve", stub_transformations
        )
        monkeypatch.setattr(gs_mod.GenerateSynthesis, "resolve", stub_synthesis)

    async def test_the_whole_call_closes_exactly_once(self, scoped_stubs):
        received = await _deepen_collecting_progress("wheel444")

        assert received, "the person saw silence for a whole deepen"
        finals = [e for e in received if e.final]
        assert len(finals) == 1, (
            f"{len(finals)} closing events for one `deepen` — a host clears its"
            f" indicator on each. Stages seen: {[e.stage for e in received]}"
        )
        assert {e.stage for e in received} == {"deepen"}, (
            "a skill's own stage name reached the channel, so it installed a scope"
            f" instead of deferring to the tool's. Got: {[e.stage for e in received]}"
        )
        assert {e.key for e in received} == {"wheel44"}, (
            "the key must be the tool's for the whole stream — a host tells two"
            " concurrent deepens apart by it"
        )

        steps = [e for e in received if not e.final and not e.note]
        assert len(steps) == 3, f"both skills' steps must survive: {steps}"
        assert finals[0].done == 3 and finals[0].total == 3, (
            "the deferred `total=1` was lost, so the bar closes short of its own"
            f" denominator: {finals[0]}"
        )

    @pytest.mark.parametrize(
        "given",
        [
            "[[a1b2c3d]]",
            "  [[a1b2c3d]]  ",
            "[a1b2c3d]",
            "a1b2c3d",
        ],
        ids=["double-brackets", "padded", "single-brackets", "clean"],
    )
    async def test_the_key_is_sanitized_before_a_host_ever_sees_it(
        self, scoped_stubs, given
    ):
        """`wheel_hash` is RAW MODEL OUTPUT, and the scope opens above any resolution.

        The framework renders pathway and wheel hashes into prompts as `[[abc1234]]`,
        so a model echoing the brackets back is the single most common malformed-hash
        shape in this tree — `audit_feasibility` already strips them for exactly that
        reason. Here the string is truncated to 7 and used as the stream key, which is
        a surface a host may render beside its spinner: unsanitized, `"[[a1b2c3d]]"`
        keyed the stream `"[[a1b2"`, putting punctuation from a prompt template in
        front of a person and — worse — giving two spellings of ONE wheel two
        different keys, which is the one thing the key exists to prevent.

        Only the KEY is sanitized, never the argument passed on: what a malformed
        hash should do to the reasoning path is `ExploreTransformations`' decision.
        """
        received = await _deepen_collecting_progress(given)

        assert received, "no events to read a key from"
        assert {e.key for e in received} == {"a1b2c3d"}, (
            f"{given!r} keyed the stream {sorted({e.key for e in received})} — the"
            f" brackets the framework itself printed reached the host"
        )

    async def test_a_missing_hash_still_produces_one_stream(self, scoped_stubs):
        """The empty key is a legitimate state and must not raise in the scope line.

        `run_deepen` is reachable with whatever the model emitted, and `(wheel_hash or
        "")` exists so a `None` slipping past the tool signature cannot turn a bad
        hash into a `TypeError` from the progress seam — the person would see a crash
        where the framework should have reported that it could not find the wheel.
        """
        received = await _deepen_collecting_progress("[[]]")

        assert received, "the person saw silence"
        assert {e.key for e in received} == {""}, (
            f"expected an empty key, got {sorted({e.key for e in received})}"
        )
        assert len([e for e in received if e.final]) == 1


class _FakeTransition:
    def __init__(self, text: str) -> None:
        self.instruction = text
        self.summary = None
        self.source = _FakeEnd()
        self.target = _FakeEnd()


class _FakeEnd:
    @staticmethod
    def get():
        return None


class _FakeManager:
    def __init__(self, transition=None) -> None:
        self._transition = transition

    def get(self):
        return (self._transition, None) if self._transition else None


class _FakeTransformation:
    """Only what `pathway_line` reads. A real Transformation needs a committed
    wheel, nexus and six transitions — this file's tests are about the caller."""

    def __init__(self, short_hash: str, recipe: str) -> None:
        self.hash = short_hash
        self.short_hash = short_hash
        self.edge = _FakeManager()
        self.ac_plus = _FakeManager(_FakeTransition(recipe))
        self.re_plus = _FakeManager()
