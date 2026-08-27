from __future__ import annotations

import time
from typing import TYPE_CHECKING, Optional

from broadcaster import Broadcast

from dialectical_framework.events.graph_event import GraphEvent
from dialectical_framework.events.progress_event import (ProgressEvent,
                                                         progress_channel)

if TYPE_CHECKING:
    from dialectical_framework.agents.execution_report import Effect


class GraphEventBus:
    """
    In-process async event bus for graph mutation fan-out.

    Uses broadcaster with memory backend. Two channels per scope: `sid` carries
    graph mutations, `sid:progress` carries work-in-flight signals.

    Lifecycle:
        bus = GraphEventBus()
        await bus.connect()      # at app startup
        ...
        await bus.disconnect()   # at app shutdown

    Publishing (from `ExecutionReport._emit`, fire-and-forget):
        await bus.publish(sid, effect)

    Subscribing (app/UI layer):
        async with bus.subscribe(sid) as subscriber:
            async for event in subscriber:
                event.message  # GraphEvent

    The two channels are deliberately separate rather than one stream of mixed
    message types: an existing subscriber sees nothing new on `sid`, so it cannot
    break, and progress is opt-in via `subscribe_progress`. See
    `events/progress_event.py` for the full reasoning and for how to read
    `done`/`total`.
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

    async def publish_progress(
        self,
        sid: str,
        *,
        stage: str,
        done: int,
        total: int,
        detail: str,
        key: Optional[str] = None,
        final: bool = False,
    ) -> None:
        """Publish a work-in-flight signal on the `sid:progress` channel.

        A no-op while disconnected, exactly like `publish` — so a host that never
        connects the bus pays nothing for the emission points, and a probe that
        forgets `connect()` sees an empty stream rather than an error.
        """
        if not self._connected:
            return
        event = ProgressEvent(
            sid=sid,
            stage=stage,
            done=done,
            total=total,
            detail=detail,
            timestamp=time.time(),
            key=key,
            final=final,
        )
        await self._broadcast.publish(channel=progress_channel(sid), message=event)

    def subscribe(self, sid: str):
        """Subscribe to graph events for a given `sid` (scope). Use as async context manager."""
        return self._broadcast.subscribe(channel=sid)

    def subscribe_progress(self, sid: str):
        """Subscribe to progress events for a given `sid`. Use as async context manager.

        Independent of `subscribe` — a host wanting both live graph updates AND a
        progress indicator runs two subscriptions. `event.message` is a
        `ProgressEvent`, never a `GraphEvent`; the channels never carry each
        other's messages.
        """
        return self._broadcast.subscribe(channel=progress_channel(sid))
