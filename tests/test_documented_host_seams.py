"""Assertions that exist because the docs make the claims.

Three host-facing seams are documented in `docs/graph.md` and `docs/agents.md`:
the event bus, input resolution, and what survives persisting `agent.messages`.
Each of those docs tells an integrator a specific, checkable thing — the payload
is on `event.message`, a URL is NOT fetched, the message list serializes
losslessly by hand. Nothing else in the suite would notice if one of them stopped
being true, because the framework's own code paths do not depend on the claim
being *documented* correctly.

So these are documentation tests. When one fails, the fix may well be the prose.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json

import pytest
from mirascope import llm
from mirascope.llm import Audio, Document, Image, Text, Thought, ToolCall, ToolOutput
from mirascope.llm.messages import AssistantMessage, SystemMessage, UserMessage

from dialectical_framework.agents.execution_report import Effect, ExecutionReport
from dialectical_framework.events.graph_event_bus import GraphEventBus
from dialectical_framework.events.progress_event import (
    PROGRESS_CHANNEL_SUFFIX,
    ProgressEvent,
    progress_channel,
)
from dialectical_framework.graph.composite_input_resolver import CompositeInputResolver
from dialectical_framework.graph.nodes.input import Input
from dialectical_framework.graph.verbatim_input_resolver import VerbatimInputResolver


@pytest.fixture(autouse=True)
def cleanup_graph_db():
    """Override autouse fixture — nothing here touches the DB."""
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    """Override autouse fixture — nothing here touches the DB."""
    yield


async def _first_message(subscribe, publish, timeout: float = 1.0):
    """Publish once and return the first envelope, or None if none arrived.

    `None` is a real outcome here, not a timeout to retry: the documented
    silent-no-op behaviour is only observable as "nothing came".
    """
    received = []

    async def consumer():
        async with subscribe() as subscriber:
            async for event in subscriber:
                received.append(event)
                break

    task = asyncio.create_task(consumer())
    await asyncio.sleep(0.05)  # let the subscription attach
    await publish()
    try:
        await asyncio.wait_for(task, timeout=timeout)
    except asyncio.TimeoutError:
        task.cancel()
    return received[0] if received else None


class TestTheEventBusPathTheDocsGive:
    """`docs/graph.md` → Events."""

    @pytest.fixture
    def effect(self):
        return Effect(seq=0, effect_type="node_created")

    async def test_the_payload_is_on_message_not_on_the_event(self, effect):
        """The documented consumer loop, exactly as written.

        This section used to show `process(event.effect)`, which raises
        `AttributeError` — the envelope comes from `broadcaster` and only the
        framework's `GraphEvent` has `effect`. A doc snippet that cannot run is
        worse than no snippet, so the working path is pinned here.
        """
        bus = GraphEventBus()
        await bus.connect()
        try:
            envelope = await _first_message(
                lambda: bus.subscribe("sid-docs"),
                lambda: bus.publish("sid-docs", effect),
            )
            assert envelope is not None, "the bus delivered nothing while connected"
            assert not hasattr(envelope, "effect"), (
                "if the envelope grows an `effect`, docs/graph.md can be "
                "simplified — until then it must say `event.message.effect`"
            )
            graph_event = envelope.message
            assert graph_event.sid == "sid-docs"
            assert graph_event.effect.effect_type == "node_created"
        finally:
            await bus.disconnect()

    async def test_publishing_without_connect_is_a_silent_no_op(self, effect):
        """The trap the docs warn about, verified rather than asserted.

        No exception, no log, no delivery — which is why a host that forgets
        `await bus.connect()` sees an empty stream and has nothing to grep for.
        """
        bus = GraphEventBus()  # deliberately not connected
        await bus.publish("sid-docs", effect)  # must not raise
        await bus.publish_progress(
            "sid-docs", stage="s", done=0, total=1, detail="d"
        )  # must not raise

        envelope = await _first_message(
            lambda: bus.subscribe("sid-docs"),
            lambda: bus.publish("sid-docs", effect),
            timeout=0.3,
        )
        assert envelope is None, (
            "publishing while disconnected delivered something — the docs' "
            "warning about a silently empty stream would be wrong"
        )

    async def test_progress_is_a_separate_channel(self):
        """`f"{sid}:progress"`, and a graph subscriber never sees it."""
        assert progress_channel("sid-docs") == "sid-docs" + PROGRESS_CHANNEL_SUFFIX
        assert progress_channel("sid-docs") != "sid-docs"

        bus = GraphEventBus()
        await bus.connect()
        try:
            envelope = await _first_message(
                lambda: bus.subscribe_progress("sid-docs"),
                lambda: bus.publish_progress(
                    "sid-docs", stage="transformation", done=1, total=4, detail="pair"
                ),
            )
            assert envelope is not None
            assert isinstance(envelope.message, ProgressEvent)
            assert (envelope.message.stage, envelope.message.total) == (
                "transformation",
                4,
            )
        finally:
            await bus.disconnect()

    def test_the_container_is_where_a_host_gets_the_bus(self, di_container):
        """`container.event_bus()` is the handle the docs point at.

        And it is the same object the framework publishes through, which is the
        part that makes it useful: a host subscribing to a *different* bus would
        see the empty stream all over again.
        """
        bus = di_container.event_bus()
        assert isinstance(bus, GraphEventBus)
        assert di_container.event_bus() is bus, "documented as a singleton"
        assert ExecutionReport._event_bus is bus, (
            "setup() wires this same instance into ExecutionReport — if that "
            "stops being true, subscribing to container.event_bus() is useless"
        )


class TestTheDefaultResolverFetchesNothing:
    """`docs/graph.md` → Input Resolution."""

    async def test_a_url_resolves_to_the_url(self):
        """The sharp edge, in one assertion.

        Nothing raises and nothing is fetched, so the pipeline analyses a
        38-character string as if it were the article. The docs say so; this is
        why they have to.
        """
        url = "https://example.com/article-about-growth"
        resolved = await VerbatimInputResolver().resolve(Input(content=url))
        assert resolved == url, (
            "if the default resolver learns to fetch, docs/graph.md and the "
            "README's 'the default fetches nothing' both need updating"
        )

    async def test_empty_content_is_empty_text_not_an_error(self):
        assert await VerbatimInputResolver().resolve(Input(content=None)) == ""

    async def test_the_wired_default_does_not_fetch_either(self, di_container):
        """The same claim one level up, where an app actually meets it.

        `VerbatimInputResolver` is only the fallback BRANCH; the default is the
        composite, and the warning is about what it does with a scheme it has no
        resolver for. Reaching through `container.input_resolver` also pins the
        provider name the documented override recipe calls `.override()` on.
        """
        resolver = di_container.input_resolver()
        assert isinstance(resolver, CompositeInputResolver)

        url = "https://example.com/article-about-growth"
        assert await resolver.resolve(Input(content=url)) == url


class TestPersistingMessages:
    """`docs/agents.md` → obligation 3."""

    def test_mirascope_messages_are_not_pydantic(self):
        """Why the docs hand out a recipe instead of `model_dump()`."""
        for cls in (SystemMessage, UserMessage, AssistantMessage):
            assert dataclasses.is_dataclass(cls)
            assert not hasattr(cls, "model_dump"), (
                "messages became Pydantic — the docs should stop hand-rolling "
                "serialization and say `model_dump()`"
            )
            assert not hasattr(cls, "model_validate")

    def test_the_part_discriminators_are_the_ones_the_docs_list(self):
        """The docs tell a host to rebuild by dispatching on these strings.

        Naming seven of them in prose is seven chances to be wrong, and a wrong
        one is only discovered by whoever tries to load a saved conversation.
        """
        documented = {
            Text: "text",
            ToolCall: "tool_call",
            ToolOutput: "tool_output",
            Thought: "thought",
            Image: "image",
            Audio: "audio",
            Document: "document",
        }
        for cls, discriminator in documented.items():
            default = {f.name: f.default for f in dataclasses.fields(cls)}["type"]
            assert default == discriminator, (
                f"{cls.__name__}.type is {default!r} — docs/agents.md lists "
                f"{discriminator!r} in its rebuild instruction"
            )

    def test_a_conversation_serializes_losslessly(self):
        """`asdict` + `json.dumps`, the documented one-liner.

        Includes the parts a role-plus-content projection would drop — a tool
        call, a tool output, and the provider payload — because those are exactly
        what the docs claim survive.
        """
        conversation = [
            llm.messages.user("Growth or sustainability?"),
            AssistantMessage(
                content=[
                    Text(text="Let me look at what we have."),
                    ToolCall(id="c1", name="present_analysis", args='{"depth":1}'),
                ],
                provider_id="anthropic",
                model_id="claude",
                provider_model_name="claude-x",
                raw_message={
                    "role": "assistant",
                    "content": [{"type": "tool_use", "id": "c1", "name": "x"}],
                },
            ),
            UserMessage(
                content=[
                    ToolOutput(id="c1", name="present_analysis", result="2 tensions")
                ]
            ),
            llm.messages.assistant("Two tensions.", model_id=None, provider_id=None),
        ]

        as_json = json.dumps([dataclasses.asdict(m) for m in conversation])
        restored = json.loads(as_json)

        assert [m["role"] for m in restored] == [
            "user",
            "assistant",
            "user",
            "assistant",
        ]
        # The discriminators the docs tell a host to rebuild on.
        assert [p["type"] for p in restored[1]["content"]] == ["text", "tool_call"]
        assert restored[1]["content"][1]["id"] == "c1"
        assert restored[2]["content"][0]["type"] == "tool_output"
        # The field the docs say not to drop, intact through JSON.
        assert restored[1]["raw_message"]["content"][0]["type"] == "tool_use"

    def test_the_content_parts_carry_bytes_as_base64_text(self):
        """Which is what makes the multimodal claim in the docs true.

        Media never reaches JSON as `bytes` — the source object holds base64
        text, so the same `asdict` recipe covers an image-bearing conversation
        with no special case.
        """
        from mirascope.llm.content.image import Base64ImageSource

        source = Base64ImageSource(
            type="base64_image_source", data="aGVsbG8=", mime_type="image/png"
        )
        restored = json.loads(json.dumps(dataclasses.asdict(source)))
        assert restored["data"] == "aGVsbG8="
        assert restored["mime_type"] == "image/png"
