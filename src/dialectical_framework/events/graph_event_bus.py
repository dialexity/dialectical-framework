from __future__ import annotations

import time
from typing import TYPE_CHECKING

from broadcaster import Broadcast

from dialectical_framework.events.graph_event import GraphEvent

if TYPE_CHECKING:
    from dialectical_framework.agents.execution_report import Effect


class GraphEventBus:
    """
    In-process async event bus for graph mutation fan-out.

    Uses broadcaster with memory backend. Channel = sid.

    Lifecycle:
        bus = GraphEventBus()
        await bus.connect()      # at app startup
        ...
        await bus.disconnect()   # at app shutdown

    Publishing (async, called from flush):
        await bus.publish(sid, effect)

    Subscribing (app/UI layer):
        async with bus.subscribe(sid) as subscriber:
            async for event in subscriber:
                event.message  # GraphEvent
    """

    def __init__(self) -> None:
        self._broadcast = Broadcast(url="memory://")
        self._connected = False

    async def connect(self) -> None:
        await self._broadcast.connect()
        self._connected = True

    async def disconnect(self) -> None:
        await self._broadcast.disconnect()
        self._connected = False

    async def publish(self, sid: str, effect: Effect) -> None:
        if not self._connected:
            return
        event = GraphEvent(sid=sid, effect=effect, timestamp=time.time())
        await self._broadcast.publish(channel=sid, message=event)

    def subscribe(self, sid: str):
        """Subscribe to graph events for a session. Use as async context manager."""
        return self._broadcast.subscribe(channel=sid)
