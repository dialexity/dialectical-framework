from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

_semaphore: asyncio.Semaphore | None = None
_disabled: bool | None = None


def _init() -> None:
    global _semaphore, _disabled
    if _disabled is not None:
        return
    raw = os.environ.get("DIALEXITY_MAX_CONCURRENT_LLM_CALLS", "0")
    try:
        limit = int(raw)
    except ValueError:
        limit = 0
    if limit > 0:
        _semaphore = asyncio.Semaphore(limit)
        _disabled = False
    else:
        _disabled = True


@asynccontextmanager
async def llm_concurrency_slot() -> AsyncIterator[None]:
    """Acquire a concurrency slot for an LLM call. Disabled by default (no-op)."""
    _init()
    if _disabled:
        yield
    else:
        assert _semaphore is not None
        async with _semaphore:
            yield
