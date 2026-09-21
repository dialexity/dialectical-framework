"""
Two models, one seam: the conversation model and the reasoning model.

`DIALEXITY_DEFAULT_MODEL` runs the conversational (tool-path) call every agent
turn makes. `DIALEXITY_REASONING_MODEL`, when set, runs every STRUCTURED call —
the framework's own reasoning (tetrads, classification, extraction,
transformations, the decision classifier) — and unset means the same model for
everything, as before. The split lives in `use_brain`, which is the one seam all
of those calls pass through, so no concern has to know.

Measured reason (rounds.md, `sonnet-thinking`): identical prompts, the
extraction concern's unsupported-claim rate is 34.6% on Haiku 4.5 and 7.0% on
Sonnet 5 — the model is the lever, not any thinking level.
"""

from __future__ import annotations

import pytest

from dialectical_framework.settings import Settings
from dialectical_framework.utils import use_brain as ub


@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


def _with_models(container, conversation: str, reasoning: str | None):
    previous = container.settings()
    container.settings.override(
        previous.model_copy(update={"ai_model": conversation, "reasoning_model": reasoning})
    )
    return previous


def _restore(container, previous) -> None:
    container.settings.reset_override()
    container.settings.override(previous)


class TestTheSettingReadsFromTheEnvironment:
    def test_default_is_unset(self):
        assert Settings.model_fields["reasoning_model"].default is None

    def test_env_sets_it_and_empty_means_unset(self, monkeypatch):
        monkeypatch.setenv("DIALEXITY_REASONING_MODEL", "bedrock/x")
        assert Settings.from_env().reasoning_model == "bedrock/x"
        monkeypatch.setenv("DIALEXITY_REASONING_MODEL", "")
        assert Settings.from_env().reasoning_model is None


class TestTheSeamRoutesByCallShape:
    def test_unset_means_one_model_for_everything(self, di_container):
        previous = _with_models(di_container, "bedrock/chat", None)
        try:
            assert ub._get_ai_model() == "bedrock/chat"
            assert ub._get_reasoning_model() == "bedrock/chat"
        finally:
            _restore(di_container, previous)

    def test_set_means_structured_calls_take_it(self, di_container):
        previous = _with_models(di_container, "bedrock/chat", "bedrock/reason")
        try:
            assert ub._get_ai_model() == "bedrock/chat"
            assert ub._get_reasoning_model() == "bedrock/reason"
        finally:
            _restore(di_container, previous)

    def test_use_brain_picks_by_format(self):
        """The one line that decides: a `format=` call resolves through the
        reasoning getter, a tool call through the conversation getter, and an
        explicit `ai_model=` wins over both. Read off the module source because
        the decorator builds the call lazily and the mock brain replaces it."""
        import inspect

        source = inspect.getsource(ub)
        assert (
            "_get_reasoning_model() if format is not None else _get_ai_model()"
            in source
        )


class TestTheBenchHoldsBothModelsToTheTier:
    def test_using_model_clears_the_reasoning_model(self, di_container):
        """A tier means "this model runs everything"; a `DIALEXITY_REASONING_MODEL`
        in a local .env must not leak into a cell and split the arm across
        two models without the archive saying so."""
        from e2e.modelctx import using_model

        previous = _with_models(di_container, "bedrock/chat", "bedrock/reason")
        try:
            with using_model(di_container, "bedrock/tier"):
                assert di_container.settings().ai_model == "bedrock/tier"
                assert di_container.settings().reasoning_model is None
                assert ub._get_reasoning_model() == "bedrock/tier"
        finally:
            _restore(di_container, previous)

    def test_the_bench_splits_only_through_its_own_knob(self, di_container, monkeypatch):
        """`DIALEXITY_E2E_REASONING_MODEL` is the one way to run a two-model
        arm, and it is what every cell records."""
        from e2e.modelctx import bench_reasoning_model, using_model

        monkeypatch.setenv("DIALEXITY_E2E_REASONING_MODEL", "bedrock/reason-tier")
        assert bench_reasoning_model() == "bedrock/reason-tier"
        previous = _with_models(di_container, "bedrock/chat", None)
        try:
            with using_model(di_container, "bedrock/tier"):
                assert di_container.settings().ai_model == "bedrock/tier"
                assert ub._get_reasoning_model() == "bedrock/reason-tier"
        finally:
            _restore(di_container, previous)
        monkeypatch.setenv("DIALEXITY_E2E_REASONING_MODEL", "")
        assert bench_reasoning_model() is None
