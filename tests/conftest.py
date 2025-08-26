import asyncio
import gc

import pytest

from dialectical_framework.dialectical_reasoning import DialecticalReasoning


@pytest.fixture(scope="session", autouse=True)
def di_container():
    """Set up DI container context for all tests"""
    container = DialecticalReasoning()
    yield container
    container.unwire()


@pytest.fixture(autouse=True)
async def cleanup_async_resources():
    """Cleanup async resources after each test"""
    yield
    # Give time for any pending operations to complete
    await asyncio.sleep(0.1)

    # Gracefully drain + stop LiteLLM worker so pytest doesn't cancel it mid-teardown
    try:
        from litellm.litellm_core_utils.logging_worker import GLOBAL_LOGGING_WORKER
        from litellm._logging import verbose_logger
        verbose_logger.exception = lambda *a, **k: None  # silence the cancel log once
        await GLOBAL_LOGGING_WORKER.clear_queue()
        await GLOBAL_LOGGING_WORKER.stop()
    except Exception:
        pass

    # Cancel all remaining tasks
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    for task in tasks:
        if not task.done():
            task.cancel()
    
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    
    # Force garbage collection to clean up any remaining references
    gc.collect()
    
    # Small delay to allow cleanup to complete
    await asyncio.sleep(0.01)


@pytest.fixture(scope="session", autouse=True)
def final_cleanup():
    """Final cleanup at the end of the test session"""
    yield
    # This runs synchronously at the end of the session
    # Force garbage collection to clean up any remaining references
    for _ in range(3):
        gc.collect()


@pytest.fixture(autouse=True)
async def cleanup_aiohttp_sessions():
    """Specifically cleanup aiohttp sessions"""
    yield
    try:
        import aiohttp
        # Look for any aiohttp sessions that might be lingering
        for obj in gc.get_objects():
            if isinstance(obj, aiohttp.ClientSession):
                if not obj.closed:
                    await obj.close()
    except ImportError:
        pass
    
    # Force garbage collection after closing sessions
    gc.collect()
    await asyncio.sleep(0.01)