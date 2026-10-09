"""
Extended-thinking request-shape compatibility.

Why this has tests at all: the failure it prevents is silent. With
`DIALEXITY_CONVERSATION_THINKING_LEVEL` set and a Claude 5 model configured, every LLM call
400s, and on the Advisor's conversational path the visible symptom is an agent
that answers with empty text and calls no tools — indistinguishable from a weak
model until you read the provider error.
"""

from __future__ import annotations

import pytest

from dialectical_framework.utils.thinking_compat import (
    ADAPTIVE,
    BUDGETED,
    OFF_BETWEEN_TOOLS,
    OFF_DISABLED,
    OFF_LOW_EFFORT,
    learn_thinking_shape_from_error,
    off_shape,
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
        """Claude 5 accepts "disabled" as sent — translating it would be noise.
        (5.5 and the Fable line do not; see `TestOffIsPerModel`.)"""
        kwargs = {"model": "global.anthropic.claude-sonnet-5", "thinking": {"type": "disabled"}}
        assert with_thinking_compat(kwargs["model"], kwargs, {})["thinking"] == {
            "type": "disabled"
        }

    def test_no_thinking_is_disabled_inside_a_conversational_round(self):
        """Bedrock's default for the adaptive shape is thinking ON, so an ABSENT
        thinking key does not mean off on a Claude 5 model. Measured 2026-09-24
        (`probe_tool_path_hidden_output`): every unset call returned a
        `thinking` block, ~500 tokens on a plain reply and ~2,500 on a
        tool-wired turn over a real graph — the sealed Advisor's 42s against the
        dump's 13s. Inside a conversational round that is double work over a
        graph that already holds the reasoning, so unset is sent as disabled."""
        from dialectical_framework.utils.thinking_compat import conversational_round

        kwargs = {"model": "global.anthropic.claude-sonnet-5", "max_tokens": 1024}
        with conversational_round():
            out = with_thinking_compat(kwargs["model"], kwargs, {})
        assert out["thinking"] == {"type": "disabled"}
        assert "thinking" not in kwargs, "input must not be mutated"

    def test_no_thinking_keeps_the_provider_default_outside_a_conversational_round(self):
        """Outside a conversational round this layer sends nothing for an
        unset level. Concerns still do not think: forced tool choice suppresses
        the provider default, and on 5.5 a call moved to JSON is sent the
        model's off by the provider's `_encode` (`test_format_compat.py`)."""
        kwargs = {"model": "global.anthropic.claude-sonnet-5", "max_tokens": 1024}
        assert "thinking" not in with_thinking_compat(kwargs["model"], kwargs, {})

    def test_no_thinking_stays_absent_on_a_budgeted_model_either_way(self):
        """A 4.x model does not think unless asked; nothing to send."""
        from dialectical_framework.utils.thinking_compat import conversational_round

        kwargs = {"model": "global.anthropic.claude-haiku-4-5-20251001-v1:0", "max_tokens": 1024}
        with conversational_round():
            assert "thinking" not in with_thinking_compat(kwargs["model"], kwargs, {})
        assert "thinking" not in with_thinking_compat(kwargs["model"], kwargs, {})

    def test_the_scope_is_left_on_exit(self):
        from dialectical_framework.utils.thinking_compat import (
            _CONVERSATIONAL_ROUND, conversational_round)

        with conversational_round():
            assert _CONVERSATIONAL_ROUND.get() is True
        assert _CONVERSATIONAL_ROUND.get() is False


class TestTheFacilitatorOpensItsRoundsInScope:
    """The four provider calls a person waits on — the tool-path call, its
    awaited resume, the streamed open and the streamed resume — are the only
    sites wrapped. Tool EXECUTION is not: a concern a tool runs must keep the
    provider default. Pinned on the source because the resumes are Mirascope's
    own requests and no runtime seam of ours sees them."""

    def test_four_sites_and_only_those(self):
        import inspect

        from dialectical_framework.agents import conversation_facilitator as cf

        src = inspect.getsource(cf.ConversationFacilitator)
        assert src.count("conversational_round()") == 4
        assert "with conversational_round():\n            return await _llm_call()" in src
        # The awaited resume runs under `retry_transient` inside the scope (the
        # round is re-asked on a transient failure, and the re-ask is a
        # conversational round too).
        assert (
            "with conversational_round():\n"
            "                        resuming = response\n"
            "                        response = await retry_transient(\n"
            "                            lambda: resuming.resume(tool_outputs), what=\"Resume\"\n"
            "                        )"
        ) in src
        assert src.count("with retry_account(turn), conversational_round():") == 2
        # Never around the tools.
        assert "conversational_round():\n                        tool_outputs = await response.execute_tools()" not in src

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


class TestOffIsPerModel:
    """How "thinking off" is said differs by model, and the wrong word is a 400
    on every conversational round (probed 2026-10-08,
    `tests/e2e/probe_claude_5_5_compat.py`): Claude 5 takes "disabled", Sonnet
    5.5 only "between_tools", Opus 5.5 has no off and takes low effort."""

    SONNET_5_5_REJECTS_DISABLED = (
        'To turn thinking off on this model, send "thinking": {"type": '
        '"between_tools"} instead of {"type": "disabled"}. The model does not '
        "think before responding."
    )
    OPUS_5_5_REJECTS_DISABLED = (
        '"thinking.type.disabled" is not supported for this model. Use '
        '"thinking.type.adaptive" and "output_config.effort" to control thinking behavior.'
    )
    REJECTS_BETWEEN_TOOLS = '"thinking.type.between_tools" is not supported for this model.'

    @pytest.mark.parametrize(
        ("model", "expected"),
        [
            ("global.anthropic.claude-sonnet-5", OFF_DISABLED),
            ("global.anthropic.claude-opus-5", OFF_DISABLED),
            ("global.anthropic.claude-sonnet-5-5", OFF_BETWEEN_TOOLS),
            ("global.anthropic.claude-opus-5-5", OFF_LOW_EFFORT),
            ("global.anthropic.claude-fable-5-5", OFF_LOW_EFFORT),
        ],
    )
    def test_off_shape_by_name(self, model: str, expected: str):
        assert off_shape(model) == expected

    @pytest.mark.parametrize(
        ("model", "thinking", "output_config"),
        [
            ("global.anthropic.claude-sonnet-5", {"type": "disabled"}, None),
            ("global.anthropic.claude-sonnet-5-5", {"type": "between_tools"}, None),
            ("global.anthropic.claude-opus-5-5", {"type": "adaptive"}, {"effort": "low"}),
        ],
    )
    def test_an_unset_level_in_a_conversational_round_is_that_models_off(
        self, model, thinking, output_config
    ):
        from dialectical_framework.utils.thinking_compat import conversational_round

        kwargs = {"model": model, "max_tokens": 1024}
        with conversational_round():
            out = with_thinking_compat(model, kwargs, {})
        assert out["thinking"] == thinking
        assert out.get("output_config") == output_config

    def test_an_explicit_disabled_is_translated_too(self):
        model = "global.anthropic.claude-sonnet-5-5"
        out = with_thinking_compat(model, {"model": model, "thinking": {"type": "disabled"}}, {})
        assert out["thinking"] == {"type": "between_tools"}

    def test_outside_a_round_nothing_is_sent_on_5_5_either(self):
        model = "global.anthropic.claude-opus-5-5"
        assert "thinking" not in with_thinking_compat(model, {"model": model}, {})

    def test_a_set_level_on_5_5_is_the_adaptive_shape(self):
        model = "global.anthropic.claude-sonnet-5-5"
        kwargs = {"model": model, "thinking": {"type": "enabled", "budget_tokens": 1638}}
        out = with_thinking_compat(model, kwargs, MEDIUM)
        assert out["thinking"] == {"type": "adaptive"}
        assert out["output_config"] == {"effort": "medium"}

    @pytest.mark.parametrize(
        ("message", "learned"),
        [
            (SONNET_5_5_REJECTS_DISABLED, OFF_BETWEEN_TOOLS),
            (OPUS_5_5_REJECTS_DISABLED, OFF_LOW_EFFORT),
            (REJECTS_BETWEEN_TOOLS, OFF_LOW_EFFORT),
        ],
    )
    def test_learns_the_off_from_the_providers_own_400(self, message, learned):
        model = "global.anthropic.claude-madeup-5"
        assert off_shape(model) == OFF_DISABLED
        assert learn_thinking_shape_from_error(model, ValueError(message))
        assert off_shape(model) == learned
        # The shape it was already sending failing again is not a shape problem.
        assert not learn_thinking_shape_from_error(model, ValueError(message))

    def test_the_off_messages_do_not_flip_the_thinking_shape(self):
        """Opus 5.5's refusal names `thinking.type.adaptive` and
        `output_config.effort`; it must not read as either shape mismatch."""
        model = "global.anthropic.claude-opus-5-5"
        learn_thinking_shape_from_error(model, ValueError(self.OPUS_5_5_REJECTS_DISABLED))
        assert thinking_shape(model) == ADAPTIVE


class TestEarlierTurnThinkingIsDroppedOnBindingModels:
    """5.5 binds a thinking block to the prefix that produced it, and the
    Advisor rebuilds its system prompt every turn — so a replayed earlier-turn
    block is a 400 on new accounts ("The block is bound to a different
    conversation … The system prompt differs", Opus 5.5 under enforcement,
    `probe_claude_5_5_compat.py`). A leading run of blocks may be removed."""

    THOUGHT = {"type": "thinking", "thinking": "", "signature": "s"}

    def _history(self):
        return [
            {"role": "user", "content": [{"type": "text", "text": "turn 1"}]},
            {"role": "assistant", "content": [dict(self.THOUGHT), {"type": "tool_use", "id": "a", "name": "t", "input": {}}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "a", "content": "x"}]},
            {"role": "assistant", "content": [dict(self.THOUGHT), {"type": "text", "text": "reply 1"}]},
            {"role": "user", "content": [{"type": "text", "text": "turn 2"}]},
            {"role": "assistant", "content": [dict(self.THOUGHT), {"type": "tool_use", "id": "b", "name": "t", "input": {}}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "b", "content": "y"}]},
        ]

    @staticmethod
    def _thoughts(messages):
        return [
            i
            for i, m in enumerate(messages)
            for b in (m["content"] if isinstance(m["content"], list) else [])
            if b.get("type") == "thinking"
        ]

    @pytest.mark.parametrize(
        "model",
        [
            "global.anthropic.claude-sonnet-5-5",
            "global.anthropic.claude-opus-5-5",
            "global.anthropic.claude-fable-5-1",
        ],
    )
    def test_earlier_turns_lose_their_blocks_and_this_turn_keeps_its_own(self, model):
        from dialectical_framework.utils.thinking_compat import without_earlier_turn_thinking

        history = self._history()
        out = without_earlier_turn_thinking(model, history)
        assert self._thoughts(out) == [5], "only the current turn's tool round keeps its block"
        assert out[1]["content"][0]["type"] == "tool_use"
        assert self._thoughts(history) == [1, 3, 5], "the history of record is not mutated"

    @pytest.mark.parametrize(
        "model",
        [
            "global.anthropic.claude-sonnet-5",
            "global.anthropic.claude-opus-5",
            "global.anthropic.claude-fable-5",
            "global.anthropic.claude-haiku-4-5-20251001-v1:0",
        ],
    )
    def test_models_that_do_not_bind_are_untouched(self, model):
        from dialectical_framework.utils.thinking_compat import without_earlier_turn_thinking

        history = self._history()
        assert without_earlier_turn_thinking(model, history) is history

    def test_the_provider_encodes_through_it(self):
        """`_encode` sends the stripped copy; the cross-turn probe is the
        live evidence that the check then passes."""
        import inspect

        from dialectical_framework.utils import bedrock_provider

        src = inspect.getsource(bedrock_provider.BedrockAnthropicProvider._encode)
        assert "without_earlier_turn_thinking(" in src


class TestReviewFindings:
    """Second-pass fixes (2026-10-08 review)."""

    THOUGHT = {"type": "thinking", "thinking": "", "signature": "s"}

    def test_a_structured_call_drops_this_turns_blocks_too(self):
        """Budget exhausted: history ends on a tool result, so no new person
        turn marks the boundary — and the structured call has no tools and,
        in JSON mode, extra system text, so the turn's own blocks are bound to
        a prefix the request no longer has."""
        from dialectical_framework.utils.thinking_compat import without_earlier_turn_thinking

        history = [
            {"role": "user", "content": [{"type": "text", "text": "turn"}]},
            {"role": "assistant", "content": [dict(self.THOUGHT), {"type": "tool_use", "id": "a", "name": "t", "input": {}}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "a", "content": "x"}]},
        ]
        model = "global.anthropic.claude-opus-5-5"
        kept = without_earlier_turn_thinking(model, history)
        assert kept[1]["content"][0]["type"] == "thinking", "a tool round keeps its own"
        out = without_earlier_turn_thinking(model, history, every_turn=True)
        assert [b["type"] for b in out[1]["content"]] == ["tool_use"]

    def test_the_provider_strips_every_turn_on_a_structured_call(self):
        import inspect

        from dialectical_framework.utils import bedrock_provider

        src = inspect.getsource(bedrock_provider.BedrockAnthropicProvider._encode)
        assert "every_turn=format is not None" in src

    def test_a_thinking_only_message_before_the_turn_is_dropped_whole(self):
        """Kept, its block would sit behind a removed run (not allowed); emptied,
        the encoder refuses it."""
        from dialectical_framework.utils.thinking_compat import without_earlier_turn_thinking

        history = [
            {"role": "user", "content": [{"type": "text", "text": "one"}]},
            {"role": "assistant", "content": [dict(self.THOUGHT)]},
            {"role": "user", "content": [{"type": "text", "text": "two"}]},
        ]
        out = without_earlier_turn_thinking("claude-sonnet-5-5", history)
        assert [m["role"] for m in out] == ["user", "user"]

    def test_an_off_refusal_on_an_unreadable_name_settles_the_shape(self):
        """An inference-profile ARN reads as budgeted; an off-shape 400 proves
        it is adaptive, or `_apply_off` never runs and the retry repeats."""
        model = "arn:aws:bedrock:eu-west-1:123:application-inference-profile/abc"
        assert thinking_shape(model) == BUDGETED
        assert learn_thinking_shape_from_error(
            model, ValueError(TestOffIsPerModel.OPUS_5_5_REJECTS_DISABLED)
        )
        assert thinking_shape(model) == ADAPTIVE
        out = with_thinking_compat(model, {"model": model, "thinking": {"type": "disabled"}}, {})
        assert out["thinking"] == {"type": "adaptive"}
        assert out["output_config"] == {"effort": "low"}

    @pytest.mark.parametrize("model", ["global.anthropic.claude-fable-5", "global.anthropic.claude-fable-5-1"])
    def test_the_fable_line_has_no_off(self, model):
        """Probed 2026-10-08: both refuse "disabled" and "between_tools"."""
        assert off_shape(model) == OFF_LOW_EFFORT


class TestTheStreamedRoundLearns:
    """The request is made when the stream manager is ENTERED, before any
    chunk — so a rejected shape can be re-sent without replaying a token."""

    @pytest.mark.asyncio
    async def test_reopens_once_with_the_learned_off(self):
        from dialectical_framework.utils.bedrock_provider import _LearningStreamManager
        from dialectical_framework.utils.thinking_compat import conversational_round

        sent = []

        class _Manager:
            def __init__(self, kwargs):
                self.kwargs = kwargs

            async def __aenter__(self):
                if self.kwargs.get("thinking") == {"type": "disabled"}:
                    raise ValueError(TestOffIsPerModel.OPUS_5_5_REJECTS_DISABLED)
                return "stream"

            async def __aexit__(self, *exc):
                return None

        class _Client:
            class messages:
                @staticmethod
                def stream(**kwargs):
                    sent.append(kwargs)
                    return _Manager(kwargs)

        model = "global.anthropic.claude-madeup-5"
        with conversational_round():
            manager = _LearningStreamManager(_Client, {"model": model, "max_tokens": 64}, {})
            async with manager as stream:
                assert stream == "stream"
        assert [k["thinking"]["type"] for k in sent] == ["disabled", "adaptive"]
        assert sent[1]["output_config"] == {"effort": "low"}
