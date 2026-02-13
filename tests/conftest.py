import asyncio
import gc
import os

import pytest
from gqlalchemy import Memgraph, Neo4j
from dependency_injector import providers

from dialectical_framework.dialectical_reasoning import DialecticalReasoning
from dialectical_framework.settings import Settings


# ============================================================================
# Test database wrappers for safe test data isolation
# ============================================================================

TEST_LABEL = "___DIALEXITY_TEST___"

# Environment variable to control test data cleanup
# Set to "false" to keep test data for inspection after tests
# Default: "true" (cleanup enabled)
TEST_CLEANUP_ENV_VAR = "DIALEXITY_TEST_CLEANUP"


def is_cleanup_enabled() -> bool:
    """
    Check if test data cleanup is enabled via environment variable.

    Returns True (cleanup enabled) by default.
    Set DIALEXITY_TEST_CLEANUP=false to disable cleanup and keep test data.
    """
    value = os.environ.get(TEST_CLEANUP_ENV_VAR, "true").lower()
    return value not in ("false", "0", "no", "off")


class TestMemgraph(Memgraph):
    """
    Wrapper around Memgraph that automatically marks all saved nodes as test data.

    This allows tests to coexist with production data safely by adding a special label.
    """

    def save_node(self, node):
        """Save node and add test label.

        For content-addressable nodes (those with hash already computed),
        look up existing node first to avoid unique constraint violations.

        IMPORTANT: Always adds test label to ALL saved nodes (even those without hash)
        so that test cleanup works correctly even when tests fail mid-execution.

        NOTE: Hash lookup includes the node's specific label to avoid
        cross-type collisions (e.g., Input and DialecticalComponent with
        same content/statement getting same hash).
        """
        # For content-addressable nodes, check if a node with this hash already exists
        if hasattr(node, 'hash') and node.hash and node._id is None:
            # Get the node's primary label for type-specific lookup
            # GQLAlchemy nodes have 'label' class attribute from @label decorator
            node_label = getattr(node.__class__, 'label', None)
            if node_label and isinstance(node_label, str):
                # Look up by hash AND specific label to avoid cross-type collisions
                query = f"""
                    MATCH (n:{node_label} {{hash: $hash}})
                    RETURN n, id(n) as node_id
                    LIMIT 1
                """
            else:
                # Fallback to generic Node label
                query = """
                    MATCH (n:Node {hash: $hash})
                    RETURN n, id(n) as node_id
                    LIMIT 1
                """
            results = list(self.execute_and_fetch(query, {"hash": node.hash}))
            if results:
                # Node exists - reuse it
                existing_node = results[0]["n"]
                node._id = results[0]["node_id"]
                # Ensure test label is set
                label_query = f"""
                    MATCH (n) WHERE id(n) = $node_id
                    SET n:{TEST_LABEL}
                """
                self.execute(label_query, {"node_id": node._id})
                return existing_node

        result = super().save_node(node)

        # Always add test label using the node ID from result
        # This handles both committed nodes (with hash) and uncommitted nodes (without hash)
        if result is not None and result._id is not None:
            label_query = f"""
                MATCH (n) WHERE id(n) = $node_id
                SET n:{TEST_LABEL}
            """
            self.execute(label_query, {"node_id": result._id})

        return result

    def save_relationship(self, relationship):
        """Save relationship normally (edges are deleted when nodes are deleted)."""
        return super().save_relationship(relationship)


class TestNeo4j(Neo4j):
    """
    Wrapper around Neo4j that automatically marks all saved nodes as test data.

    This allows tests to coexist with production data safely by adding a special label.
    """

    def save_node(self, node):
        """Save node and add test label.

        For content-addressable nodes (those with hash already computed),
        look up existing node first to avoid unique constraint violations.

        IMPORTANT: Always adds test label to ALL saved nodes (even those without hash)
        so that test cleanup works correctly even when tests fail mid-execution.

        NOTE: Hash lookup includes the node's specific label to avoid
        cross-type collisions (e.g., Input and DialecticalComponent with
        same content/statement getting same hash).
        """
        # For content-addressable nodes, check if a node with this hash already exists
        if hasattr(node, 'hash') and node.hash and node._id is None:
            # Get the node's primary label for type-specific lookup
            # GQLAlchemy nodes have 'label' class attribute from @label decorator
            node_label = getattr(node.__class__, 'label', None)
            if node_label and isinstance(node_label, str):
                # Look up by hash AND specific label to avoid cross-type collisions
                query = f"""
                    MATCH (n:{node_label} {{hash: $hash}})
                    RETURN n, id(n) as node_id
                    LIMIT 1
                """
            else:
                # Fallback to generic Node label
                query = """
                    MATCH (n:Node {hash: $hash})
                    RETURN n, id(n) as node_id
                    LIMIT 1
                """
            results = list(self.execute_and_fetch(query, {"hash": node.hash}))
            if results:
                # Node exists - reuse it
                existing_node = results[0]["n"]
                node._id = results[0]["node_id"]
                # Ensure test label is set
                label_query = f"""
                    MATCH (n) WHERE id(n) = $node_id
                    SET n:{TEST_LABEL}
                """
                self.execute(label_query, {"node_id": node._id})
                return existing_node

        result = super().save_node(node)

        # Always add test label using the node ID from result
        # This handles both committed nodes (with hash) and uncommitted nodes (without hash)
        if result is not None and result._id is not None:
            label_query = f"""
                MATCH (n) WHERE id(n) = $node_id
                SET n:{TEST_LABEL}
            """
            self.execute(label_query, {"node_id": result._id})

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


def _create_test_graph_db(settings: Settings):
    """
    Factory method to create the appropriate test graph database wrapper.

    Similar to the production factory but returns Test wrappers for safety.
    """
    vendor = settings.graph_db_vendor.lower()

    # Common parameters for both vendors
    common_params = {
        "host": settings.graph_db_host,
        "port": settings.graph_db_port,
        "username": settings.graph_db_username,
        "password": settings.graph_db_password,
        "encrypted": settings.graph_db_encrypted,
        "client_name": settings.graph_db_client_name,
    }

    if vendor == "neo4j":
        # Neo4j requires username/password, provide defaults if not set
        if not common_params["username"]:
            common_params["username"] = "neo4j"
        if not common_params["password"]:
            common_params["password"] = "neo4j"

        db = TestNeo4j(**common_params)

    elif vendor == "memgraph":
        db = TestMemgraph(**common_params)

    else:
        raise ValueError(
            f"Unknown graph_db_vendor: {vendor}. "
            f"Supported vendors: 'memgraph', 'neo4j'"
        )

    # Ensure schema indexes exist (same as production)
    DialecticalReasoning._ensure_schema(db)
    return db


@pytest.fixture(scope="session", autouse=True)
def di_container():
    """Set up DI container context for all tests with Test wrapper."""
    container = DialecticalReasoning.setup(Settings.from_env())

    # Override graph_db factory to use Test wrapper (TestMemgraph or TestNeo4j)
    container.graph_db.override(
        providers.Singleton(
            _create_test_graph_db,
            settings=container.settings
        )
    )

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
    # Note: Removed gc.get_objects() iteration as it's extremely slow
    # when there are many objects in memory (e.g., after graph tests).
    # aiohttp sessions should be closed explicitly where created.
    gc.collect()
    await asyncio.sleep(0.01)


# ============================================================================
# Graph database fixtures for testing
# ============================================================================

def is_graph_db_available(settings: Settings) -> bool:
    """Check if the configured graph database is running."""
    vendor = settings.graph_db_vendor.lower()

    # Common parameters for both vendors
    common_params = {
        "host": settings.graph_db_host,
        "port": settings.graph_db_port,
        "username": settings.graph_db_username,
        "password": settings.graph_db_password,
        "encrypted": settings.graph_db_encrypted,
        "client_name": settings.graph_db_client_name,
    }

    try:
        if vendor == "memgraph":
            db = Memgraph(**common_params)
        elif vendor == "neo4j":
            # Neo4j requires username/password, provide defaults if not set
            if not common_params["username"]:
                common_params["username"] = "neo4j"
            if not common_params["password"]:
                common_params["password"] = "neo4j"
            db = Neo4j(**common_params)
        else:
            return False

        db.execute("RETURN 1")
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def graph_db_available(di_container)-> bool:
    """Check if the configured graph database is available for tests."""
    settings = di_container.settings()
    return is_graph_db_available(settings)


@pytest.fixture(autouse=True)
def cleanup_graph_db(graph_db_available, di_container):
    """
    Auto-cleanup fixture for all graph DB tests.

    Automatically skips tests if the configured graph database is not available.
    Cleans up test data before and after each test (when cleanup is enabled).

    SAFETY: Only deletes nodes labeled with :___DIALEXITY_TEST___
    This allows tests to run safely alongside production data.

    Control cleanup behavior via environment variable:
        DIALEXITY_TEST_CLEANUP=true   (default) - cleanup before/after each test
        DIALEXITY_TEST_CLEANUP=false  - keep test data for inspection

    When cleanup is re-enabled, all past test data (with TEST_LABEL) is cleared
    on the next test run.
    """
    settings = di_container.settings()
    if not graph_db_available:
        pytest.skip(
            f"{settings.graph_db_vendor} is not available. "
            f"Please start the database and try again."
        )

    db = di_container.graph_db()
    cleanup_enabled = is_cleanup_enabled()

    if cleanup_enabled:
        cleanup_test_data(db)

    yield

    if cleanup_enabled:
        try:
            cleanup_test_data(db)
        except Exception:
            pass  # Ignore cleanup errors


