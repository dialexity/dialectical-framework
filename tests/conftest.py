import asyncio
import gc

import pytest
from gqlalchemy import Memgraph

from dialectical_framework.dialectical_reasoning import DialecticalReasoning
from dialectical_framework.settings import Settings


@pytest.fixture(scope="session", autouse=True)
def di_container():
    """Set up DI container context for all tests"""
    container = DialecticalReasoning.setup(Settings.from_env())
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


# ============================================================================
# Memgraph fixtures for graph testing
# ============================================================================

def is_memgraph_available():
    """Check if Memgraph is running."""
    try:
        db = Memgraph(host="127.0.0.1", port=7687)
        db.execute("RETURN 1")
        return True
    except Exception:
        return False


TEST_LABEL = "___DIALEXITY_TEST___"


class TestMemgraph(Memgraph):
    """
    Wrapper around Memgraph that automatically marks all saved nodes as test data.

    This allows tests to coexist with production data safely by adding a special label.
    """

    def save_node(self, node):
        """Save node and add test label."""
        result = super().save_node(node)

        # Add test label after saving (query by uid since _id isn't populated)
        if hasattr(node, 'uid') and node.uid:
            labels = ':'.join(node.__class__.__name__.split())
            query = f"""
            MATCH (n:{labels} {{uid: $uid}})
            SET n:{TEST_LABEL}
            """
            self.execute(query, {"uid": node.uid})

        return result

    def save_relationship(self, relationship):
        """Save relationship normally (edges are deleted when nodes are deleted)."""
        return super().save_relationship(relationship)


def cleanup_test_data(db):
    """Delete only test data (nodes with TEST_LABEL)."""
    query = f"""
    MATCH (n:{TEST_LABEL})
    DETACH DELETE n
    """
    db.execute(query)


@pytest.fixture(scope="session")
def memgraph_available():
    """Check if Memgraph is available for tests."""
    return is_memgraph_available()


@pytest.fixture
def db(memgraph_available):
    """
    Create a Memgraph connection for testing.

    Automatically skips tests if Memgraph is not available.

    SAFETY: Only deletes nodes labeled with :___DIALEXITY_TEST___
    This allows tests to run safely alongside production data.

    To start Memgraph for testing:
        docker-compose -f docker-compose.test.yml up -d

    To run tests:
        poetry run pytest tests/test_graph.py
    """
    if not memgraph_available:
        pytest.skip(
            "Memgraph is not available. "
            "Run: docker-compose -f docker-compose.test.yml up -d"
        )

    # Connect to Memgraph using test wrapper
    db = TestMemgraph(host="127.0.0.1", port=7687)

    # Clear only test data before each test
    cleanup_test_data(db)

    yield db

    # Cleanup only test data after test
    try:
        cleanup_test_data(db)
    except Exception:
        pass  # Ignore cleanup errors