"""The transformation audit is an opt-in analytical annotation, not a build step.

WHY THESE TESTS
===============
`TransformationAudit` was 40% of `explore`'s entire provider spend — two calls per
Transformation, 12 calls / 147.4s at 1 PP — and nothing in the framework branches
on what it writes. It is now gated on `settings.audit_transformations`, default
off. The claims worth pinning, in order of what would hurt most if they broke:

1. **Off by default, and off really means zero calls.** The whole point is the
   latency; a gate that still constructs the auditor buys nothing.
2. **On still works.** A flag that quietly disables a feature permanently is
   worse than no flag, and the only caller is behind two other conditions
   (`all_new`, and the progress scope) that could swallow it.
3. **Skipping is not a shortfall.** An unaudited wheel is FINISHED. If the report
   ever starts calling it partial, `deepen` will re-run forever topping up work
   that was never owed.
4. **The progress denominator drops the audit steps with it.** They were
   `expect_progress(len(all_new))`; left behind, every bar would stall one step
   short of its total for the rest of the run.
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest


@contextmanager
def _settings(di_container, **overrides):
    current = di_container.settings()
    di_container.settings.override(current.model_copy(update=overrides))
    try:
        yield
    finally:
        di_container.settings.reset_override()
        di_container.settings.override(current)


@pytest.fixture(autouse=True)
def cleanup_graph_db():
    """Override — the audit gate is decided before any DB access."""
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    """Override — the audit gate is decided before any DB access."""
    yield


class _FakeWheel:
    short_hash = "wheel42"


class _FakeNexus:
    short_hash = "nexus42"


class _FakeTransformation:
    """Just enough to be counted as `new`."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.hash = f"hash-{name}"
        self.short_hash = name


@pytest.fixture
def driven(monkeypatch):
    """Drive `ExploreTransformations.resolve()` with two new Transformations.

    Everything up to the audit is stubbed: the gate under test is a single
    condition at step 5, and reaching it through the real pipeline would need a
    live wheel, a nexus and 30-odd provider calls.
    """
    from dialectical_framework.agents.explorer.skills import \
        explore_transformations as et_mod
    from dialectical_framework.concerns import transformation_audit as ta_mod

    audited: list = []

    async def fake_audit(self, transformation, input_text="", audit_all=False):
        audited.append(transformation)
        self._report.summary = "audited"
        return []

    monkeypatch.setattr(ta_mod.TransformationAudit, "resolve", fake_audit)

    async def fake_pair(self, wheel, nexus, edge_a, edge_b, input_text):
        return [], [_FakeTransformation("t1"), _FakeTransformation("t2")], None

    monkeypatch.setattr(
        et_mod.ExploreTransformations, "_resolve_wheel", lambda self: _FakeWheel()
    )
    monkeypatch.setattr(
        et_mod.ExploreTransformations,
        "_resolve_nexus",
        staticmethod(lambda wheel: _FakeNexus()),
    )
    monkeypatch.setattr(
        et_mod.ExploreTransformations,
        "_get_target_edge_pairs",
        lambda self, wheel: [(object(), object())],
    )

    async def fake_input(self):
        return "input text"

    monkeypatch.setattr(et_mod.ExploreTransformations, "_get_input_text", fake_input)
    monkeypatch.setattr(et_mod.ExploreTransformations, "_process_edge_pair", fake_pair)

    def _run():
        return et_mod.ExploreTransformations(wheel_hash="wheel42")

    return _run, audited


class TestTheAuditIsOffByDefault:

    def test_the_setting_defaults_to_off(self, di_container):
        """The default is the whole change — assert it, don't infer it."""
        assert di_container.settings().audit_transformations is False

    @pytest.mark.asyncio
    async def test_no_audit_runs_with_the_default_setting(self, di_container, driven):
        make, audited = driven
        with _settings(di_container, audit_transformations=False):
            skill = make()
            result = await skill.resolve()

        assert len(result.new) == 2, "the fixture must actually produce new work"
        assert audited == [], (
            "the audit ran with the setting off — the 40% of provider spend this"
            " gate exists to reclaim is still being spent"
        )

    @pytest.mark.asyncio
    async def test_skipping_the_audit_is_not_reported_as_a_shortfall(
        self, di_container, driven
    ):
        """An unaudited wheel is finished, not partial.

        If this ever fails, `deepen` starts topping up work that was never owed
        and the Advisor presents a complete wheel as a fragment.
        """
        make, audited = driven
        with _settings(di_container, audit_transformations=False):
            skill = make()
            await skill.resolve()

        report = skill.report
        assert report.ok is not False
        assert "still_missing" not in report.artifacts
        assert "audit" not in str(report).lower(), (
            "the report mentions the audit — a skipped annotation is not news the"
            " agent can act on, and reads as missing work"
        )


class TestTheAuditStillRunsWhenAskedFor:

    @pytest.mark.asyncio
    async def test_every_new_transformation_is_audited_once(self, di_container, driven):
        make, audited = driven
        with _settings(di_container, audit_transformations=True):
            skill = make()
            result = await skill.resolve()

        assert len(audited) == len(result.new) == 2
        assert {t.name for t in audited} == {"t1", "t2"}

    @pytest.mark.asyncio
    async def test_nothing_new_means_nothing_audited_even_when_on(
        self, di_container, monkeypatch, driven
    ):
        """`all_new` guards the branch first — an idempotent re-run pays nothing."""
        from dialectical_framework.agents.explorer.skills import \
            explore_transformations as et_mod

        make, audited = driven

        async def only_existing(self, wheel, nexus, edge_a, edge_b, input_text):
            return [_FakeTransformation("old")], [], None

        monkeypatch.setattr(
            et_mod.ExploreTransformations, "_process_edge_pair", only_existing
        )

        with _settings(di_container, audit_transformations=True):
            skill = make()
            result = await skill.resolve()

        assert result.new == []
        assert audited == []


class TestTheProgressDenominatorFollowsTheGate:
    """The audit's steps were `expect_progress(len(all_new))`.

    Left in place with the audit gone, `total` would exceed the steps that can
    ever be reported and every host's bar would stall one short of its own total
    for the rest of the run — a stuck indicator on a finished build.
    """

    @pytest.mark.asyncio
    async def test_the_final_total_excludes_audit_steps_when_off(
        self, di_container, driven
    ):
        totals = await self._final_counts(di_container, driven, audit=False)
        assert totals.total == totals.done, (
            f"denominator {totals.total} but only {totals.done} steps reported —"
            " the audit's expectation outlived the audit"
        )

    @pytest.mark.asyncio
    async def test_the_audit_steps_are_counted_when_on(self, di_container, driven):
        totals = await self._final_counts(di_container, driven, audit=True)
        assert totals.total == totals.done == 2, (
            "two new transformations, so two audit steps expected and reported"
        )

    @staticmethod
    async def _final_counts(di_container, driven, *, audit: bool):
        """Capture the scope at the moment it closes.

        Read from the scope object rather than the bus: this asserts the
        arithmetic, and routing it through a channel would only add a way for the
        test to be flaky about delivery.
        """
        from dialectical_framework.utils import progress as progress_module

        make, _ = driven
        captured: list = []
        real_scope = progress_module.progress_scope

        @contextmanager
        def spy(stage, **kwargs):
            with real_scope(stage, **kwargs) as scope:
                captured.append(scope)
                yield scope

        from dialectical_framework.agents.explorer.skills import \
            explore_transformations as et_mod

        original = et_mod.progress_scope
        et_mod.progress_scope = spy
        try:
            with _settings(di_container, audit_transformations=audit):
                await make().resolve()
        finally:
            et_mod.progress_scope = original

        assert len(captured) == 1, "one scope per tool call, keyed by wheel"
        return captured[0]
