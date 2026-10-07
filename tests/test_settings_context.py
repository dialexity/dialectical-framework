"""Settings per request (`settings_context`): a ContextVar over a process base.

What is pinned: outside any scope a read sees the base `setup()` installed;
inside `using_settings` it sees that value, restored on exit, innermost winning;
two concurrent tasks each see their own (the defect: one global slot made two
requests answer on each other's model); tasks started inside inherit; every
read path the framework has (`Provide[DI.settings]`, `SettingsAware.settings`,
`use_brain`'s model getters) goes through it; `container.settings.override`
raises; the graph connection is built from the BASE. DB-free.
"""

from __future__ import annotations

import asyncio

import pytest
from dependency_injector import providers

from dialectical_framework.dialectical_reasoning import DialecticalReasoning
from dialectical_framework.protocols.has_config import SettingsAware
from dialectical_framework.settings_context import (get_base_settings,
                                                    get_current_settings,
                                                    using_settings)
from dialectical_framework.utils import use_brain as ub


@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


def _with(model: str):
    return using_settings(get_base_settings().model_copy(update={"ai_model": model, "reasoning_model": None}))


class _Reader(SettingsAware):
    pass


def test_outside_any_scope_the_base_is_read(di_container):
    assert di_container.settings() is get_base_settings()
    assert get_current_settings() is get_base_settings()


def test_a_scope_holds_inside_and_restores_on_exit(di_container):
    base_model = get_base_settings().ai_model
    with _with("bedrock/one"):
        assert di_container.settings().ai_model == "bedrock/one"
        assert _Reader().settings.ai_model == "bedrock/one", "SettingsAware reads the scope"
        assert ub._get_ai_model() == "bedrock/one", "use_brain's resolver reads the scope"
        with _with("bedrock/two"):
            assert di_container.settings().ai_model == "bedrock/two", "innermost wins"
        assert di_container.settings().ai_model == "bedrock/one", "outer restored"
    assert di_container.settings().ai_model == base_model


@pytest.mark.asyncio
async def test_two_concurrent_requests_see_only_their_own(di_container):
    """The defect this exists to end: with one global slot, the second
    request's choice reached the first request's calls in flight."""

    async def request(model: str) -> list[str]:
        seen = []
        with _with(model):
            for _ in range(5):
                seen.append(_Reader().settings.ai_model)
                await asyncio.sleep(0)  # interleave with the other request
                seen.append(ub._get_ai_model())
        return seen

    a, b = await asyncio.gather(request("bedrock/alice"), request("bedrock/bob"))
    assert set(a) == {"bedrock/alice"} and set(b) == {"bedrock/bob"}


@pytest.mark.asyncio
async def test_tasks_started_inside_inherit_the_scope(di_container):
    """The framework's own fan-out (best-of-N draws, the judge, the off-turn
    weave) runs in tasks created inside the request."""

    async def child() -> str:
        await asyncio.sleep(0)
        return _Reader().settings.ai_model

    with _with("bedrock/parent"):
        gathered = await asyncio.gather(child(), child())
        spawned = await asyncio.create_task(child())
    assert gathered == ["bedrock/parent", "bedrock/parent"] and spawned == "bedrock/parent"


def test_override_is_refused_and_names_the_replacement(di_container):
    """An override would swap the per-request provider for one fixed object and
    put the whole process back on a single slot — silently."""
    with pytest.raises(RuntimeError, match="using_settings"):
        di_container.settings.override(providers.Object(get_base_settings()))


def test_the_graph_connection_is_built_from_the_base():
    """One connection per process: if it read the per-request settings, the
    first request to resolve it would choose the database for everyone."""
    assert DialecticalReasoning.graph_db.kwargs["settings"] is DialecticalReasoning.base_settings
