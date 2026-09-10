"""Tests for the graph event bus."""

from __future__ import annotations

import asyncio

import pytest

from dialectical_framework.agents.execution_report import Effect, ExecutionReport, NodeRef
from dialectical_framework.events.graph_event import GraphEvent
from dialectical_framework.events.graph_event_bus import GraphEventBus


@pytest.fixture(autouse=True)
def cleanup_graph_db():
    """Override — this test module doesn't need the DB."""
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    """Override — this test module doesn't need the DB."""
    yield


@pytest.fixture
async def bus():
    b = GraphEventBus()
    await b.connect()
    yield b
    await b.disconnect()


class TestGraphEventBus:

    @pytest.mark.asyncio
    async def test_publish_no_subscribers(self, bus: GraphEventBus):
        """Publishing with no subscribers is a no-op."""
        effect = Effect(
            seq=0,
            effect_type="node_created",
            node=NodeRef(label="Statement", hash="abc1234"),
        )
        await bus.publish("test-sid", effect)

    @pytest.mark.asyncio
    async def test_single_subscriber_receives_event(self, bus: GraphEventBus):
        """A subscriber receives published events for its channel."""
        effect = Effect(
            seq=0,
            effect_type="node_created",
            node=NodeRef(label="Statement", hash="abc1234"),
        )

        received = []

        async def consumer():
            async with bus.subscribe("test-sid") as subscriber:
                async for event in subscriber:
                    received.append(event)
                    break  # exit after first event

        task = asyncio.create_task(consumer())
        await asyncio.sleep(0.05)
        await bus.publish("test-sid", effect)
        await asyncio.wait_for(task, timeout=1.0)

        assert len(received) == 1
        assert received[0].message.sid == "test-sid"
        assert received[0].message.effect.effect_type == "node_created"
        assert received[0].message.effect.node.label == "Statement"

    @pytest.mark.asyncio
    async def test_sid_filtering(self, bus: GraphEventBus):
        """Subscriber only receives events for its channel (sid)."""
        effect = Effect(
            seq=0,
            effect_type="node_created",
            node=NodeRef(label="Statement", hash="abc1234"),
        )

        received = []

        async def consumer():
            async with bus.subscribe("sid-A") as subscriber:
                async for event in subscriber:
                    received.append(event)
                    break

        task = asyncio.create_task(consumer())
        await asyncio.sleep(0.05)

        # Publish to different sid — should not be received
        await bus.publish("sid-B", effect)
        await asyncio.sleep(0.05)

        # Publish to matching sid
        await bus.publish("sid-A", effect)
        await asyncio.wait_for(task, timeout=1.0)

        assert len(received) == 1
        assert received[0].message.sid == "sid-A"

    @pytest.mark.asyncio
    async def test_multiple_subscribers_fan_out(self, bus: GraphEventBus):
        """Multiple subscribers on the same channel all receive the event."""
        effect = Effect(
            seq=0,
            effect_type="node_updated",
            node=NodeRef(label="Perspective", hash="def5678"),
            patch={"discarded": "not relevant"},
        )

        received_1 = []
        received_2 = []

        async def consumer_1():
            async with bus.subscribe("test-sid") as subscriber:
                async for event in subscriber:
                    received_1.append(event)
                    break

        async def consumer_2():
            async with bus.subscribe("test-sid") as subscriber:
                async for event in subscriber:
                    received_2.append(event)
                    break

        task1 = asyncio.create_task(consumer_1())
        task2 = asyncio.create_task(consumer_2())
        await asyncio.sleep(0.05)

        await bus.publish("test-sid", effect)
        await asyncio.wait_for(asyncio.gather(task1, task2), timeout=1.0)

        assert len(received_1) == 1
        assert len(received_2) == 1
        assert received_1[0].message.effect.patch == {"discarded": "not relevant"}


class TestExecutionReportEventIntegration:
    """Swaps the CLASS-LEVEL bus, so every test here must put it back.

    `ExecutionReport.set_event_bus` writes a class attribute and `di_container` is
    session-scoped, so `set_event_bus(None)` in a `finally` is not a teardown — it
    unwires the container's own bus for every test that runs after this module, and
    the symptom is silent: reports still buffer, tools still return the right answer,
    and only a test that SUBSCRIBES notices it received nothing. That is exactly how
    `test_graph.py::test_perspective_combination_delivers_effects_while_it_runs`
    failed in the suite while passing alone. Restore the previous value, the way the
    progress-test modules do with `progress_module.set_event_bus(previous)`.
    """

    @pytest.fixture(autouse=True)
    def restore_execution_report_bus(self):
        previous = ExecutionReport._event_bus
        yield
        ExecutionReport.set_event_bus(previous)

    @pytest.mark.asyncio
    async def test_report_publishes_via_bus(self, bus: GraphEventBus):
        """ExecutionReport._buffer publishes effects when bus is set."""
        from unittest.mock import MagicMock
        from dialectical_framework.graph.scope_context import scope

        ExecutionReport.set_event_bus(bus)
        try:
            received = []

            async def consumer():
                async with bus.subscribe("integration-sid") as subscriber:
                    async for event in subscriber:
                        received.append(event)
                        break

            task = asyncio.create_task(consumer())
            await asyncio.sleep(0.05)

            with scope("integration-sid"):
                report = ExecutionReport(tool="test_tool")
                # Create a mock node
                node = MagicMock()
                node.__class__.__name__ = "Statement"
                node.short_hash = "abc1234"
                node.text = "Test statement"
                report.node_created(node)

            await asyncio.wait_for(task, timeout=1.0)

            assert len(received) == 1
            assert received[0].message.effect.effect_type == "node_created"
            assert received[0].message.effect.node.label == "Statement"
        finally:
            ExecutionReport.set_event_bus(None)

    @pytest.mark.asyncio
    async def test_report_no_publish_without_bus(self):
        """ExecutionReport._buffer is a no-op when bus is not set."""
        from unittest.mock import MagicMock

        ExecutionReport.set_event_bus(None)

        report = ExecutionReport(tool="test_tool")
        node = MagicMock()
        node.__class__.__name__ = "Statement"
        node.short_hash = "abc1234"
        node.text = "Test"
        # Should not raise
        report.node_created(node)

    @pytest.mark.asyncio
    async def test_report_no_publish_without_scope(self, bus: GraphEventBus):
        """ExecutionReport._buffer is a no-op when no sid in scope."""
        from unittest.mock import MagicMock

        ExecutionReport.set_event_bus(bus)
        try:
            report = ExecutionReport(tool="test_tool")
            node = MagicMock()
            node.__class__.__name__ = "Statement"
            node.short_hash = "abc1234"
            node.text = "Test"
            # No scope set — should not crash or publish
            report.node_created(node)
            await asyncio.sleep(0.05)
        finally:
            ExecutionReport.set_event_bus(None)
