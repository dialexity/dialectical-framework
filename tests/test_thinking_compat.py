"""
Extended-thinking request-shape compatibility.

Why this has tests at all: the failure it prevents is silent. With
`DIALEXITY_THINKING_LEVEL` set and a Claude 5 model configured, every LLM call
400s, and on the Advisor's conversational path the visible symptom is an agent
that answers with empty text and calls no tools — indistinguishable from a weak
model until you read the provider error.
"""

from __future__ import annotations

import pytest

from dialectical_framework.utils.thinking_compat import (
    ADAPTIVE,
    BUDGETED,
    learn_thinking_shape_from_error,
    reset_learned_thinking_shapes,
    thinking_shape,
    with_thinking_compat,
)

pytestmark = []


@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


@pytest.fixture(autouse=True)
def _forget_learned_shapes():
    """The learned map is process-global; leaking it across tests hides bugs."""
    reset_learned_thinking_shapes()
    yield
    reset_learned_thinking_shapes()


BUDGETED_KWARGS = {
    "model": "global.anthropic.claude-sonnet-5",
    "max_tokens": 4096,
    "thinking": {"type": "enabled", "budget_tokens": 1638},
}
MEDIUM = {"thinking": {"level": "medium"}}


class TestShapeSelection:
    @pytest.mark.parametrize(
        "model",
        [
            "global.anthropic.claude-sonnet-5",
            "global.anthropic.claude-opus-5",
            "global.anthropic.claude-fable-5",
        ],
    )
    def test_claude_5_wants_adaptive(self, model: str):
        assert thinking_shape(model) == ADAPTIVE

    @pytest.mark.parametrize(
        "model",
        [
            # Verified against Bedrock: this model rejects BOTH halves of the
            # adaptive shape.
            "global.anthropic.claude-haiku-4-5-20251001-v1:0",
            "us.anthropic.claude-sonnet-4-20250514-v1:0",
            # 3.x puts the version before the family — must not read as 5.
            "anthropic.claude-3-5-sonnet-20241022-v2:0",
        ],
    )
    def test_pre_5_wants_budgeted(self, model: str):
        assert thinking_shape(model) == BUDGETED


class TestTranslation:
    def test_adaptive_model_gets_adaptive_plus_effort(self):
        out = with_thinking_compat(BUDGETED_KWARGS["model"], BUDGETED_KWARGS, MEDIUM)
        assert out["thinking"] == {"type": "adaptive"}
        assert out["output_config"] == {"effort": "medium"}

    def test_budgeted_model_is_left_alone(self):
        model = "global.anthropic.claude-haiku-4-5-20251001-v1:0"
        out = with_thinking_compat(model, BUDGETED_KWARGS, MEDIUM)
        assert out["thinking"] == BUDGETED_KWARGS["thinking"]
        assert "output_config" not in out

    def test_input_is_not_mutated(self):
        """The retry path re-translates from the same base kwargs."""
        before = dict(BUDGETED_KWARGS["thinking"])
        with_thinking_compat(BUDGETED_KWARGS["model"], BUDGETED_KWARGS, MEDIUM)
        assert BUDGETED_KWARGS["thinking"] == before

    def test_disabled_passes_through_untouched(self):
        """Both shapes accept "disabled" — translating it would be noise."""
        kwargs = {"model": "global.anthropic.claude-sonnet-5", "thinking": {"type": "disabled"}}
        assert with_thinking_compat(kwargs["model"], kwargs, {})["thinking"] == {
            "type": "disabled"
        }

    def test_no_thinking_stays_absent(self):
        kwargs = {"model": "global.anthropic.claude-sonnet-5", "max_tokens": 1024}
        assert "thinking" not in with_thinking_compat(kwargs["model"], kwargs, {})

    def test_unknown_level_drops_effort_but_still_adapts(self):
        """A bad level must not resurrect the shape the model rejects."""
        out = with_thinking_compat(
            BUDGETED_KWARGS["model"], BUDGETED_KWARGS, {"thinking": {"level": "turbo"}}
        )
        assert out["thinking"] == {"type": "adaptive"}
        assert "output_config" not in out


class TestLearningFromErrors:
    ENABLED_REJECTED = (
        '"thinking.type.enabled" is not supported for this model. Use '
        '"thinking.type.adaptive" and "output_config.effort" to control thinking behavior.'
    )

    def test_learns_adaptive_from_the_400(self):
        model = "bedrock-only-future-model"
        assert thinking_shape(model) == BUDGETED
        assert learn_thinking_shape_from_error(model, ValueError(self.ENABLED_REJECTED))
        assert thinking_shape(model) == ADAPTIVE

    @pytest.mark.parametrize(
        "message",
        [
            "adaptive thinking is not supported on this model",
            "output_config.effort: Extra inputs are not permitted",
        ],
    )
    def test_learns_budgeted_from_the_400(self, message: str):
        model = "global.anthropic.claude-madeup-5"
        assert thinking_shape(model) == ADAPTIVE
        assert learn_thinking_shape_from_error(model, ValueError(message))
        assert thinking_shape(model) == BUDGETED

    def test_unrelated_errors_do_not_trigger_a_retry(self):
        """Otherwise a real fault gets one silent extra API call and the same
        exception, doubling cost and confusing the trace."""
        assert not learn_thinking_shape_from_error(
            "m", ValueError("ThrottlingException: slow down")
        )

    def test_does_not_loop_when_the_shape_was_not_the_problem(self):
        model = "m"
        assert learn_thinking_shape_from_error(model, ValueError(self.ENABLED_REJECTED))
        assert not learn_thinking_shape_from_error(
            model, ValueError(self.ENABLED_REJECTED)
        )
