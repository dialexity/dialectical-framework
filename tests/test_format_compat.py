"""
Structured-call formatting mode, per model.

Claude 5.5 refuses forced tool use (`tool_choice` of type `tool`/`any`), which is
Mirascope's default structured format and the one every concern uses; with a 5.5
model configured every structured call 400s (probed 2026-10-08,
`tests/e2e/probe_claude_5_5_compat.py`). `format_compat` re-asks those calls in
JSON mode, and the Bedrock provider encodes through it.
"""

from __future__ import annotations

import pytest
from mirascope import llm
from mirascope.llm.formatting.format import Format
from pydantic import BaseModel

from dialectical_framework.utils.format_compat import (
    claude_version,
    learn_format_mode_from_error,
    refuses_forced_tool_use,
    reset_learned_format_modes,
    with_format_compat,
)


@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


@pytest.fixture(autouse=True)
def _forget_learned_modes():
    reset_learned_format_modes()
    yield
    reset_learned_format_modes()


class SmallDto(BaseModel):
    word: str


REJECTED = 'tool_choice: type "tool" and "any" are not supported for this model.'


class TestVersionReading:
    @pytest.mark.parametrize(
        ("model", "version"),
        [
            ("global.anthropic.claude-sonnet-5", (5, 0)),
            ("global.anthropic.claude-sonnet-5-5", (5, 5)),
            ("global.anthropic.claude-opus-5-5", (5, 5)),
            ("global.anthropic.claude-haiku-4-5-20251001-v1:0", (4, 5)),
            ("anthropic.claude-sonnet-4-20250514-v1:0", (4, 0)),
            ("anthropic.claude-3-5-sonnet-20241022-v2:0", None),
        ],
    )
    def test_a_date_suffix_is_never_a_minor(self, model, version):
        assert claude_version(model) == version


class TestModeSelection:
    @pytest.mark.parametrize(
        "model",
        ["global.anthropic.claude-sonnet-5-5", "global.anthropic.claude-opus-5-5"],
    )
    def test_a_bare_dto_goes_as_json_to_5_5(self, model):
        out = with_format_compat(model, SmallDto)
        assert isinstance(out, Format)
        assert out.mode == "json" and out.formattable is SmallDto

    def test_an_explicit_tool_mode_goes_as_json_to_5_5(self):
        out = with_format_compat("claude-opus-5-5", llm.format(SmallDto, mode="tool"))
        assert out.mode == "json"

    @pytest.mark.parametrize(
        "model",
        [
            "global.anthropic.claude-sonnet-5",
            "global.anthropic.claude-haiku-4-5-20251001-v1:0",
        ],
    )
    def test_models_that_take_forced_tool_use_keep_it(self, model):
        """Every measured figure was taken on forced tool use; switching a
        model that accepts it is a measurement, not a compatibility fix."""
        assert with_format_compat(model, SmallDto) is SmallDto

    def test_another_explicit_mode_is_left_alone(self):
        fmt = llm.format(SmallDto, mode="strict")
        assert with_format_compat("claude-sonnet-5-5", fmt) is fmt

    def test_no_format_passes_through(self):
        assert with_format_compat("claude-sonnet-5-5", None) is None


class TestLearning:
    def test_learns_from_the_providers_400(self):
        model = "global.anthropic.claude-madeup-5"
        assert not refuses_forced_tool_use(model)
        assert learn_format_mode_from_error(model, SmallDto, ValueError(REJECTED))
        assert with_format_compat(model, SmallDto).mode == "json"
        # Already JSON and still failing: not the mode.
        assert not learn_format_mode_from_error(model, SmallDto, ValueError(REJECTED))

    def test_unrelated_errors_and_unforced_requests_do_not_retry(self):
        assert not learn_format_mode_from_error("m", SmallDto, ValueError("Throttling"))
        assert not learn_format_mode_from_error("m", None, ValueError(REJECTED))
        assert not learn_format_mode_from_error(
            "m", llm.format(SmallDto, mode="json"), ValueError(REJECTED)
        )


class TestTheProviderEncodesThroughIt:
    """The request the Bedrock provider builds: no forced tool choice for 5.5."""

    def _encode(self, model_id):
        from mirascope.llm.tools import AsyncToolkit

        from dialectical_framework.utils.bedrock_provider import BedrockAnthropicProvider

        return BedrockAnthropicProvider._encode(
            model_id, [llm.messages.user("Name a colour.")], AsyncToolkit(tools=[]), SmallDto, {}
        )

    def test_5_5_request_has_no_tool_choice(self):
        _, resolved, kwargs = self._encode("bedrock/global.anthropic.claude-sonnet-5-5")
        assert "tool_choice" not in kwargs
        assert resolved.mode == "json"
        assert kwargs["model"] == "global.anthropic.claude-sonnet-5-5"

    def test_5_0_request_keeps_forced_tool_use(self):
        _, resolved, kwargs = self._encode("bedrock/global.anthropic.claude-sonnet-5")
        assert kwargs["tool_choice"]["type"] in ("tool", "any")
        assert resolved.mode == "tool"

    def test_a_moved_call_keeps_not_thinking(self):
        """Forced tool choice kept structured calls from thinking; JSON mode
        with nothing sent is thinking ON. The moved call says off, and the
        thinking layer turns that into the model's own off."""
        from dialectical_framework.utils.thinking_compat import with_thinking_compat

        for model, off in (
            ("global.anthropic.claude-sonnet-5-5", {"type": "between_tools"}),
            ("global.anthropic.claude-opus-5-5", {"type": "adaptive"}),
        ):
            _, _, kwargs = self._encode(f"bedrock/{model}")
            assert kwargs["thinking"] == {"type": "disabled"}
            assert with_thinking_compat(model, kwargs, {})["thinking"] == off

    def test_a_call_that_asked_to_think_keeps_its_thinking(self):
        from mirascope.llm.tools import AsyncToolkit

        from dialectical_framework.utils.bedrock_provider import BedrockAnthropicProvider

        _, _, kwargs = BedrockAnthropicProvider._encode(
            "bedrock/global.anthropic.claude-sonnet-5-5",
            [llm.messages.user("Name a colour.")],
            AsyncToolkit(tools=[]),
            SmallDto,
            {"thinking": {"level": "medium"}, "max_tokens": 4096},
        )
        assert kwargs["thinking"]["type"] == "enabled"

    def test_an_unmoved_call_sends_no_thinking_key(self):
        _, _, kwargs = self._encode("bedrock/global.anthropic.claude-sonnet-5")
        assert "thinking" not in kwargs


class TestReviewFindings:
    def test_fable_5_1_refuses_and_fable_5_accepts(self):
        """Probed 2026-10-08."""
        assert refuses_forced_tool_use("global.anthropic.claude-fable-5-1")
        assert not refuses_forced_tool_use("global.anthropic.claude-fable-5")

    def test_a_parameterised_generic_is_re_asked_too(self):
        out = with_format_compat("claude-sonnet-5-5", list[str])
        assert isinstance(out, Format) and out.mode == "json"

    def test_another_tool_choice_complaint_does_not_move_the_model(self):
        model = "global.anthropic.claude-madeup-5"
        message = "tool_choice.disable_parallel_tool_use: not supported for this model."
        assert not learn_format_mode_from_error(model, SmallDto, ValueError(message))
        assert not refuses_forced_tool_use(model)

    def test_a_model_already_sent_as_json_is_not_retried(self):
        assert not learn_format_mode_from_error(
            "global.anthropic.claude-sonnet-5-5", SmallDto, ValueError(REJECTED)
        )

    @pytest.mark.asyncio
    async def test_the_awaited_call_re_encodes_once_after_the_400(self):
        """The retry in `_call_async`, end to end with a fake client: forced
        tool use first, the provider's 400, then the same call in JSON."""
        from mirascope.llm.tools import AsyncToolkit
        from test_model_refusal import _message

        from dialectical_framework.utils.bedrock_provider import BedrockAnthropicProvider

        sent = []

        class _Messages:
            async def create(self, **kwargs):
                sent.append(kwargs)
                if "tool_choice" in kwargs:
                    raise ValueError(REJECTED)
                return _message("end_turn", text='{"word": "teal"}')

        provider = BedrockAnthropicProvider.__new__(BedrockAnthropicProvider)
        provider.async_client = type("C", (), {"messages": _Messages()})()
        response = await provider._call_async(
            model_id="bedrock/global.anthropic.claude-madeup-5",
            messages=[llm.messages.user("Name a colour.")],
            toolkit=AsyncToolkit(tools=[]),
            format=SmallDto,
        )
        assert len(sent) == 2
        assert "tool_choice" in sent[0] and "tool_choice" not in sent[1]
        assert response.parse().word == "teal"


class TestAJsonModeCallIsConstrainedToItsSchema:
    """JSON mode on a 5.5 model is sent as a structured output
    (`output_config.format`): the host measured 32 parse re-asks in 80 cards
    without it (`probe_structured_outputs.py` for the acceptance matrix)."""

    def _encode(self, model_id, format=SmallDto, params=None):
        from mirascope.llm.tools import AsyncToolkit

        from dialectical_framework.utils.bedrock_provider import BedrockAnthropicProvider

        return BedrockAnthropicProvider._encode(
            model_id, [llm.messages.user("Name a colour.")], AsyncToolkit(tools=[]), format, params or {}
        )

    @pytest.mark.parametrize(
        "model",
        ["bedrock/global.anthropic.claude-sonnet-5-5", "bedrock/global.anthropic.claude-opus-5-5"],
    )
    def test_a_substituted_call_carries_the_schema(self, model):
        _, resolved, kwargs = self._encode(model)
        assert resolved.mode == "json"
        constraint = kwargs["output_config"]["format"]
        assert constraint["type"] == "json_schema"
        schema = constraint["schema"]
        assert schema["additionalProperties"] is False
        assert schema["required"] == ["word"]
        assert set(schema["properties"]) == {"word"}

    def test_an_explicit_json_mode_call_carries_it_too(self):
        """The two thinking writers ask for JSON mode themselves; on 5.5 they
        re-asked as often as the substituted calls (7 of 240 view draws)."""
        _, _, kwargs = self._encode(
            "bedrock/global.anthropic.claude-sonnet-5-5", llm.format(SmallDto, mode="json")
        )
        assert kwargs["output_config"]["format"]["type"] == "json_schema"

    def test_the_effort_and_the_format_share_one_output_config(self):
        """`with_thinking_compat` folds the model's effort into `output_config`
        after the format was placed there; neither may evict the other."""
        from dialectical_framework.utils.thinking_compat import with_thinking_compat

        _, _, kwargs = self._encode(
            "bedrock/global.anthropic.claude-opus-5-5",
            params={"thinking": {"level": "medium"}, "max_tokens": 4096},
        )
        sent = with_thinking_compat("global.anthropic.claude-opus-5-5", kwargs, {"thinking": {"level": "medium"}})
        assert sent["output_config"]["effort"] == "medium"
        assert sent["output_config"]["format"]["type"] == "json_schema"
        # The moved call's "off" on Opus 5.5 is low effort, in the same dict.
        _, _, off = self._encode("bedrock/global.anthropic.claude-opus-5-5")
        sent_off = with_thinking_compat("global.anthropic.claude-opus-5-5", off, {})
        assert sent_off["output_config"] == {
            "format": off["output_config"]["format"],
            "effort": "low",
        }

    @pytest.mark.parametrize(
        "model",
        ["bedrock/global.anthropic.claude-sonnet-5", "bedrock/global.anthropic.claude-haiku-4-5"],
    )
    def test_a_model_on_forced_tool_use_is_untouched(self, model):
        """Sonnet 5 took the constraint in the probe too, but every judged
        figure there was taken without it — widening it is a measurement."""
        _, resolved, kwargs = self._encode(model)
        assert resolved.mode == "tool"
        assert "output_config" not in kwargs
        _, _, explicit = self._encode(model, llm.format(SmallDto, mode="json"))
        assert "output_config" not in explicit

    def test_a_primitive_or_parser_format_gets_no_constraint(self):
        from dialectical_framework.utils.format_compat import structured_output_format

        assert structured_output_format("global.anthropic.claude-sonnet-5-5", llm.format(list[str], mode="json")) is None
        assert structured_output_format("global.anthropic.claude-sonnet-5-5", None) is None

    def test_the_schema_is_the_sdks_strict_transform(self):
        """Pinned because the transform is imported from the SDK's private
        `_parse` module: a rename there must fail here, not in production."""
        from anthropic.lib._parse._transform import transform_schema

        from dialectical_framework.utils.format_compat import structured_output_format

        got = structured_output_format("global.anthropic.claude-sonnet-5-5", llm.format(SmallDto, mode="json"))
        assert got == {"type": "json_schema", "schema": transform_schema(SmallDto)}
