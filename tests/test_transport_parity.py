"""
Bedrock and the Anthropic API are ONE instrument.

A deployment points `DIALEXITY_DEFAULT_MODEL` at `bedrock/...` or at
`anthropic/...`, and until 2026-10-26 that choice silently changed what the
framework sent: the whole compat layer lived in `BedrockAnthropicProvider`, so a
native call went out with Mirascope's defaults — forced tool use on a model that
refuses it, JSON asked for in prose with no schema constraint, thinking on by
default in conversation, earlier turns' thinking blocks replayed under a rebuilt
system prompt, the cache breakpoint behind the Advisor's mutable dump, and the
SDK's own retries under the ladder. Then a judged figure measured on one
transport said nothing about the other (the native run of
`probe_view_turn_ask.py`, 2026-10-26: CC 36/40 against an archive's 24/40,
which is the missing output constraint and not the prompts).

These tests pin the fix: the layer lives on `_AnthropicTransport`, both
providers inherit the whole of it, and one request of one kind encodes the same
way on either transport apart from the model's own name.
"""

from __future__ import annotations

import inspect

import pytest
from mirascope import llm
from mirascope.llm.tools import Toolkit
from pydantic import BaseModel

from dialectical_framework.utils import bedrock_provider as bp
from dialectical_framework.utils.bedrock_provider import (
    BedrockAnthropicProvider, NativeAnthropicProvider, _AnthropicTransport)
from dialectical_framework.utils.thinking_compat import (
    conversational_round, reset_learned_thinking_shapes, with_thinking_compat)


@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


@pytest.fixture(autouse=True)
def _forget_learned_shapes():
    reset_learned_thinking_shapes()
    yield
    reset_learned_thinking_shapes()


class SmallDto(BaseModel):
    word: str


#: The same model, as each transport spells it.
SONNET_55 = {
    "bedrock": "bedrock/global.anthropic.claude-sonnet-5-5-20260401-v1:0",
    "anthropic": "anthropic/claude-sonnet-5-5",
}
PROVIDERS = {"bedrock": BedrockAnthropicProvider, "anthropic": NativeAnthropicProvider}

#: Every method of the compat layer. A new one belongs on the base class, or it
#: is a difference between the transports that nobody measured.
LAYER = (
    "_encode",
    "_create_async",
    "_create_sync",
    "_call_async",
    "_call",
    "_stream_async",
    "_provider_model_name",
)


def encode(transport: str, *, format=SmallDto, params=None, messages=None):
    """One request, encoded by the named transport's provider."""
    return PROVIDERS[transport]._encode(
        model_id=SONNET_55[transport],
        messages=messages or [llm.messages.user("hi")],
        toolkit=Toolkit(tools=[]),
        format=format,
        params=params or {},
    )


class TestTheLayerIsSharedNotCopied:
    """The point of the refactor: one definition, two clients."""

    @pytest.mark.parametrize("name", LAYER)
    @pytest.mark.parametrize("transport", sorted(PROVIDERS))
    def test_both_providers_inherit_the_same_function(self, name, transport):
        """Neither subclass may override a compat method — an override is how
        the two transports became two instruments in the first place."""
        own = vars(PROVIDERS[transport])
        assert name not in own, (
            f"{PROVIDERS[transport].__name__} overrides {name}; the compat layer "
            "belongs on _AnthropicTransport so both transports get it"
        )
        assert name in vars(_AnthropicTransport)

    def test_the_subclasses_differ_only_in_their_client(self):
        """What a subclass is allowed to define: its identity and its client."""
        for cls in PROVIDERS.values():
            defined = {
                n for n, v in vars(cls).items()
                if not n.startswith("__") and (inspect.isfunction(v) or n in ("id", "default_scope"))
            }
            assert defined <= {"id", "default_scope", "__init__"}, (
                f"{cls.__name__} defines {defined - {'id', 'default_scope', '__init__'}}"
            )

    def test_neither_transport_builds_the_beta_provider(self):
        """Strict structured output is a third formatting mode, and no judged
        figure in this tree was taken on it (see `_AnthropicTransport`)."""
        for cls in PROVIDERS.values():
            assert "_beta_provider = None" in inspect.getsource(cls.__init__)
        for name in ("_call_async", "_call", "_stream_async"):
            assert "_beta_provider" not in inspect.getsource(
                getattr(_AnthropicTransport, name)
            )

    def test_both_clients_leave_every_retry_to_the_ladder(self):
        """`_SDK_MAX_RETRIES = 0` and the framework's read timeout on BOTH, or a
        native stall runs to the SDK's 600s and is retried below the ladder,
        where `retry_accounting` cannot see it."""
        for cls in PROVIDERS.values():
            src = inspect.getsource(cls.__init__)
            assert src.count("max_retries=_SDK_MAX_RETRIES") == 2, cls.__name__
            assert "_client_timeout(connect_timeout_s, read_timeout_s)" in src


class TestOneRequestEncodesTheSameWay:
    """The wire, compared term by term across the two transports."""

    def test_the_model_name_is_the_only_difference_in_a_structured_call(self):
        _, bedrock_format, bedrock = encode("bedrock")
        _, native_format, native = encode("anthropic")
        assert bedrock.pop("model") != native.pop("model")
        assert bedrock == native
        assert bedrock_format.mode == native_format.mode == "json"

    def test_both_carry_the_schema_constraint(self):
        """JSON asked for in prose is what the native run measured as a
        different instrument; the constraint is the seam that was missing."""
        for transport in PROVIDERS:
            _, _, kwargs = encode(transport)
            constraint = (kwargs.get("output_config") or {}).get("format")
            assert constraint and constraint["type"] == "json_schema", transport

    def test_both_send_a_structured_call_with_thinking_off(self):
        for transport in PROVIDERS:
            _, _, kwargs = encode(transport)
            assert kwargs["thinking"] == {"type": "disabled"}, transport

    def test_both_relocate_the_cache_breakpoint_off_the_mutable_dump(self):
        system = (
            "E" * 30_000 + bp.CACHE_SPLIT_SENTINEL + "the graph, which moves every turn"
        )
        encoded = []
        for transport in PROVIDERS:
            _, _, kwargs = encode(
                transport,
                format=None,
                messages=[llm.messages.system(system), llm.messages.user("hi")],
            )
            blocks = kwargs["system"]
            assert isinstance(blocks, list) and len(blocks) == 2, transport
            assert blocks[0]["cache_control"]["ttl"] == bp._CACHE_TTL, transport
            assert "cache_control" not in blocks[1], transport
            encoded.append(blocks)
        assert encoded[0] == encoded[1]

    def test_both_drop_earlier_turns_thinking_on_a_binding_model(self):
        """One function, reached through the shared `_encode`."""
        src = inspect.getsource(_AnthropicTransport._encode)
        assert "without_earlier_turn_thinking(" in src
        assert "every_turn=format is not None" in src


class TestThinkingIsDecidedTheSameWayOnBoth:
    """The one place the two transports are not symmetric underneath:
    Mirascope 2.8.2 reads a native model's bare name and translates the shape
    itself, while Bedrock's prefixed inference-profile name never matches its
    pattern. The wire must come out the same anyway."""

    def test_a_level_lands_on_the_same_effort(self):
        """The two level tables differ — Mirascope has no `xhigh` and sends any
        level it cannot read as `medium` — so without the framework re-deriving
        it, the same configured level would think less natively."""
        wire = {}
        for transport in PROVIDERS:
            _, _, kwargs = encode(
                transport, format=None, params={"thinking": {"level": "xhigh"}}
            )
            out = with_thinking_compat(
                kwargs["model"], kwargs, {"thinking": {"level": "xhigh"}}
            )
            wire[transport] = (out["thinking"], out["output_config"]["effort"])
        assert wire["bedrock"] == ({"type": "adaptive"}, "xhigh")
        assert wire["bedrock"] == wire["anthropic"]

    def test_mirascope_really_does_translate_natively_and_not_on_bedrock(self):
        """The premise of the branch above. If this ever flips, the branch is
        dead code and the comment on it is a lie."""
        _, _, native = encode(
            "anthropic", format=None, params={"thinking": {"level": "medium"}}
        )
        _, _, bedrock = encode(
            "bedrock", format=None, params={"thinking": {"level": "medium"}}
        )
        assert native["thinking"] == {"type": "adaptive"}
        assert bedrock["thinking"]["type"] == "enabled", "a token budget, as 2.5 sent"

    def test_an_unset_level_is_off_in_conversation_on_both(self):
        """"No hidden thinking where you consult" was a Bedrock-only policy: a
        native conversational turn took the provider default, which is ON."""
        off = {}
        for transport in PROVIDERS:
            model = PROVIDERS[transport]._provider_model_name(SONNET_55[transport])
            with conversational_round():
                out = with_thinking_compat(model, {"model": model}, {})
            off[transport] = out["thinking"]
        assert off["bedrock"] == {"type": "between_tools"}, "Sonnet 5.5's own off"
        assert off["bedrock"] == off["anthropic"]


class TestTheNativeScopeIsRegistered:
    """Registering is what makes any of the above reach the wire: Mirascope
    auto-registers `anthropic/` on first use otherwise."""

    def test_use_brain_registers_each_transport_on_its_own_prefix(self):
        # The module's own text: the mocked suite replaces `use_brain` itself
        # (`tests/mock_brain.py`), so reading the attribute would read the mock.
        import pathlib

        import dialectical_framework.utils.use_brain as module

        src = pathlib.Path(module.__file__).read_text(encoding="utf-8")
        assert 'resolved.startswith("bedrock/")' in src
        assert 'resolved.startswith("anthropic/")' in src
        assert "ensure_anthropic_provider()" in src

    def test_an_explicit_registration_beats_mirascopes_auto_registration(self):
        from mirascope.llm.providers import provider_registry as registry

        previous = dict(registry.PROVIDER_REGISTRY)
        previously_registered = dict(bp._registered)
        try:
            registry.PROVIDER_REGISTRY.clear()
            bp._registered.clear()
            bp.ensure_anthropic_provider()
            resolved = registry.get_provider_for_model("anthropic/claude-sonnet-5-5")
            assert isinstance(resolved, NativeAnthropicProvider)
        finally:
            registry.PROVIDER_REGISTRY.clear()
            registry.PROVIDER_REGISTRY.update(previous)
            bp._registered.clear()
            bp._registered.update(previously_registered)

    def test_registration_is_idempotent_and_per_scope(self):
        from mirascope.llm.providers import provider_registry as registry

        previous = dict(registry.PROVIDER_REGISTRY)
        previously_registered = dict(bp._registered)
        try:
            registry.PROVIDER_REGISTRY.clear()
            bp._registered.clear()
            bp.ensure_anthropic_provider()
            first = registry.PROVIDER_REGISTRY["anthropic/"]
            bp.ensure_anthropic_provider()
            assert registry.PROVIDER_REGISTRY["anthropic/"] is first
            # A deployment can run the chat on one transport and the reasoning
            # model on the other, so one flag would have blocked the second.
            bp.ensure_bedrock_provider()
            assert isinstance(
                registry.PROVIDER_REGISTRY["bedrock/"], BedrockAnthropicProvider
            )
            assert registry.PROVIDER_REGISTRY["anthropic/"] is first
        finally:
            registry.PROVIDER_REGISTRY.clear()
            registry.PROVIDER_REGISTRY.update(previous)
            bp._registered.clear()
            bp._registered.update(previously_registered)


class TestTheLayerIsClaudeVersionDriftAndNothingElse:
    """The claim recorded in CLAUDE.md and `streaming-latency-and-retry.md`:
    this layer is not a provider abstraction, it is Anthropic version drift,
    and it passes a non-Claude request through untouched. The risk it guards
    is someone broadening a name heuristic and silently reshaping another
    vendor's requests — the heuristics are the only thing keeping the layer
    scoped, since `use_brain` hands any model id to whichever provider the
    registry resolves."""

    NOT_CLAUDE = ("gpt-5.2", "gpt-4o", "o4-mini", "gemini-3-pro", "llama-4-70b")

    @pytest.mark.parametrize("name", NOT_CLAUDE)
    def test_every_shim_is_a_no_op_on_a_non_claude_name(self, name):
        from dialectical_framework.utils.format_compat import (
            claude_version, refuses_forced_tool_use, structured_output_format,
            with_format_compat)
        from dialectical_framework.utils.thinking_compat import (
            ADAPTIVE, binds_thinking_to_prefix, thinking_shape)

        assert claude_version(name) is None, "the one read everything else keys on"
        assert refuses_forced_tool_use(name) is False
        assert with_format_compat(name, SmallDto) is SmallDto, "format untouched"
        assert structured_output_format(name, SmallDto) is None, "no constraint added"
        assert thinking_shape(name) != ADAPTIVE, "no shape translation"
        assert binds_thinking_to_prefix(name) is False, "history untouched"

    @pytest.mark.parametrize("name", NOT_CLAUDE)
    def test_a_conversational_round_does_not_turn_thinking_off_for_it(self, name):
        """The off policy is a Claude-5 answer to a Claude-5 default (thinking
        ON for the adaptive shape). On a model whose default is off, sending an
        off shape would be inventing a parameter."""
        with conversational_round():
            out = with_thinking_compat(name, {"model": name}, {})
        assert "thinking" not in out

    def test_both_spellings_of_one_model_read_the_same_version(self):
        """Bedrock's inference profile and the bare native name are the SAME
        model, and every heuristic has to see that or the two transports drift
        apart again by name alone."""
        from dialectical_framework.utils.format_compat import (
            claude_family, claude_version, refuses_forced_tool_use)
        from dialectical_framework.utils.thinking_compat import (
            binds_thinking_to_prefix, off_shape, thinking_shape)

        reads = []
        for transport in PROVIDERS:
            name = PROVIDERS[transport]._provider_model_name(SONNET_55[transport])
            reads.append((
                claude_version(name),
                claude_family(name),
                refuses_forced_tool_use(name),
                thinking_shape(name),
                off_shape(name),
                binds_thinking_to_prefix(name),
            ))
        assert reads[0] == reads[1], dict(zip(sorted(PROVIDERS), reads))


class TestBothTransportsStripOutputOnlyFields:
    """The strip has to sit at the PROVIDER, not in the facilitator: the tool
    loop's resumes are Mirascope's own requests and never pass through
    `ConversationFacilitator`, and the 400 that found this was on a resume.

    These tests also pin the ONE asymmetry left between the transports, which
    is Mirascope's and not ours: `_encode_message` replays an assistant turn's
    `raw_message` verbatim only when `message.provider_id == "anthropic"`
    (`providers/anthropic/_utils/encode.py`). Our Bedrock responses carry
    `provider_id="bedrock"`, so there every assistant turn is REBUILT from
    decoded content, while natively it is echoed. That is why the
    `parsed_output` 400 was reachable only on the native transport, and it is
    why this test asserts a different thing per transport rather than the same
    thing twice — a Bedrock arm written as "no parsed_output survives" passes
    whether or not the strip exists, which is a test that proves nothing.
    Unifying the two replay paths would be a measurement, not a cleanup: it
    changes what every Bedrock figure in the archive was taken on."""

    RAW = {
        "role": "assistant",
        # The shape the API hands back on a constrained call.
        "content": [{"type": "text", "text": "ok", "parsed_output": {"word": "x"}}],
    }

    def _history(self, transport):
        return [
            llm.messages.user("hi"),
            llm.messages.assistant(
                "ok",
                model_id=SONNET_55[transport],
                provider_id=PROVIDERS[transport].id,
                raw_message=dict(self.RAW),
            ),
            llm.messages.user("and now?"),
        ]

    @staticmethod
    def _blocks(kwargs):
        return [
            block
            for message in kwargs["messages"]
            for block in (
                message["content"] if isinstance(message.get("content"), list) else []
            )
            if isinstance(block, dict)
        ]

    def test_the_shared_encode_strips_them(self):
        src = inspect.getsource(_AnthropicTransport._encode)
        assert "without_output_only_fields(" in src

    def test_the_native_transport_replays_the_turn_and_strips_the_field(self):
        """The arm with teeth: natively the raw block IS the request, so
        without the strip `parsed_output` reaches the provider and 400s."""
        _, _, kwargs = encode("anthropic", format=None, messages=self._history("anthropic"))
        texts = [b for b in self._blocks(kwargs) if b.get("type") == "text"]
        assert {"type": "text", "text": "ok"} in texts, (
            "the replay path was not taken, so this arm proves nothing about the strip"
        )
        assert not any("parsed_output" in b for b in self._blocks(kwargs))

    def test_bedrock_rebuilds_the_turn_instead_of_replaying_it(self):
        """Not a second proof of the strip — a pin on WHY the 400 never
        appeared on Bedrock, so nobody reads its absence as evidence that the
        strip is unnecessary."""
        history = self._history("bedrock")
        _, _, kwargs = encode("bedrock", format=None, messages=history)
        assert not any("parsed_output" in b for b in self._blocks(kwargs))
        assert history[1].raw_message["content"][0]["parsed_output"] == {"word": "x"}, (
            "the history of record must still hold what the model actually sent"
        )
        # The tell: the replay path keeps the raw list identity, the rebuild
        # does not. If Mirascope ever drops the provider_id check, this fails
        # and the docs above need rewriting.
        assert kwargs["messages"][1]["content"] is not history[1].raw_message["content"]
