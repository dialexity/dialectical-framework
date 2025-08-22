import pytest

from dialectical_framework.dialectical_reasoning import DialecticalReasoning


@pytest.fixture(scope="session", autouse=True)
def di_container():
    """Set up DI container context for all tests"""
    container = DialecticalReasoning()
    yield container
    container.unwire()