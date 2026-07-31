"""
Tests for Settings.from_partial merge semantics.

Only EXPLICITLY SET fields on the partial override env defaults
(exclude_unset). A field merely carrying its Pydantic default must not stomp
an env-configured value — the historical exclude_none merge did exactly
that for every non-Optional field.
"""

from __future__ import annotations

import pytest

from dialectical_framework.settings import Settings

# DB-free: override the autouse graph fixtures with empty yields.


@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


@pytest.fixture
def env_configured(monkeypatch):
    """Simulate an operator's env: non-default budget values."""
    monkeypatch.setenv("DIALEXITY_DEFAULT_MODEL", "anthropic/test-model")
    monkeypatch.setenv("DIALEXITY_ADVISOR_WHEEL_QUALITY_TOP_PLAUSIBLE", "5")
    monkeypatch.setenv("DIALEXITY_DEFAULT_COMPONENT_LENGTH", "9")


class TestFromPartial:
    def test_none_returns_env(self, env_configured):
        s = Settings.from_partial(None)
        assert s.advisor_wheel_quality_top_plausible == 5
        assert s.component_length == 9

    def test_unset_fields_do_not_stomp_env(self, env_configured):
        """The historical bug: a partial set only for ai_model dragged every
        other field's Pydantic default over the env-configured values."""
        partial = Settings(ai_model="openai/other-model")
        s = Settings.from_partial(partial)

        assert s.ai_model == "openai/other-model"
        # env values survive — NOT the field defaults (3 / 7)
        assert s.advisor_wheel_quality_top_plausible == 5
        assert s.component_length == 9

    def test_explicitly_set_fields_override_env(self, env_configured):
        partial = Settings(
            ai_model="openai/other-model", advisor_wheel_quality_top_plausible=10
        )
        s = Settings.from_partial(partial)
        assert s.advisor_wheel_quality_top_plausible == 10
        assert s.component_length == 9  # untouched

    def test_explicit_default_value_still_overrides(self, env_configured):
        """Setting a field explicitly to the same value as its Pydantic
        default is still an explicit set — it overrides env."""
        partial = Settings(ai_model="openai/other-model", advisor_wheel_quality_top_plausible=3)
        s = Settings.from_partial(partial)
        assert s.advisor_wheel_quality_top_plausible == 3

    def test_explicit_none_never_unsets_env(self, env_configured, monkeypatch):
        monkeypatch.setenv("DIALEXITY_GRAPH_DB_USERNAME", "env-user")
        partial = Settings(
            ai_model="openai/other-model", graph_db_username=None
        )
        s = Settings.from_partial(partial)
        assert s.graph_db_username == "env-user"
