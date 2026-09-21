"""
Structured calls can think — but only in JSON formatting mode.

Every concern DTO reaches the provider through
`ConversationFacilitator._call_with_response_model`, whose default formatting
mode is forced tool use, and the provider rejects extended thinking on that
shape ("Thinking may not be enabled when tool_choice forces tool use"). So the
framework's own reasoning has never thought, whatever `conversation_thinking_level` said —
that setting reaches only the conversational tool path.

`ConversationFacilitator(format_mode="json", thinking=...)` is the door:
Mirascope's JSON mode parses a DTO-shaped call 4/4 with less prefill than tool
mode and accepts thinking (`tests/e2e/probe_format_mode_thinking.py`).
No concern opts in — by decision, after measuring it. These tests pin the
plumbing DB-free: what reaches `use_brain`, that the shape travels through
`isolate()`, that the impossible combination is refused at construction, and
that no setting wires it anywhere.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator


@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


class _Dto(BaseModel):
    answer: str


class TestTheShapeThatReachesTheProvider:
    """`_structured_request` is what `_call_with_response_model` hands
    `use_brain`; pinned on the helper because the mock brain replaces the
    caller wholesale, and it also pins that the caller still uses it."""

    def test_the_caller_uses_the_helper(self):
        """Read off the MODULE source: the mock brain replaces the method on
        the class for the whole suite, so the method object's source is the
        mock's."""
        import inspect

        import dialectical_framework.agents.conversation_facilitator as cf_module

        source = inspect.getsource(cf_module)
        assert "requested, thinking_kwargs = self._structured_request(response_model)" in source
        assert "@use_brain(format=requested, **thinking_kwargs)" in source

    def test_the_default_is_a_bare_dto_with_no_thinking(self):
        requested, kwargs = ConversationFacilitator()._structured_request(_Dto)
        assert requested is _Dto
        assert kwargs == {}

    def test_json_mode_with_thinking(self):
        conversation = ConversationFacilitator(format_mode="json", thinking="medium")
        requested, kwargs = conversation._structured_request(_Dto)
        assert requested is not _Dto
        assert requested.mode == "json"
        assert requested.formattable is _Dto
        assert kwargs == {"thinking": "medium"}

    def test_json_mode_alone_carries_no_thinking(self):
        requested, kwargs = ConversationFacilitator(format_mode="json")._structured_request(_Dto)
        assert requested.mode == "json"
        assert kwargs == {}


class TestTheImpossibleCombinationIsRefusedEarly:
    def test_thinking_without_json_mode_raises_at_construction(self):
        with pytest.raises(ValueError, match="format_mode='json'"):
            ConversationFacilitator(thinking="medium")
        with pytest.raises(ValueError, match="format_mode='json'"):
            ConversationFacilitator(format_mode="tool", thinking="low")


class TestTheShapeTravelsThroughIsolate:
    def test_isolate_copies_mode_and_thinking(self):
        parent = ConversationFacilitator(format_mode="json", thinking="low")
        parent.set_system_prompt("s")
        child = parent.isolate()
        assert child._format_mode == "json"
        assert child._structured_thinking == "low"
        bare = ConversationFacilitator().isolate(keep_history=False)
        assert bare._format_mode is None and bare._structured_thinking is None


class TestNoConcernIsWiredToIt:
    """The capability exists without a caller, by decision: thinking on the
    extraction concern was priced on both tiers and bought nothing, and the
    setting that wired it was removed. A concern that reaches for it again
    needs its own A/B first."""

    def test_extraction_runs_in_the_default_shape(self, di_container):
        from dialectical_framework.concerns.thesis_extraction import \
            ThesisExtraction

        concern = ThesisExtraction()
        assert concern._conversation._format_mode is None
        assert concern._conversation._structured_thinking is None

    def test_there_is_no_setting_for_it(self):
        from dialectical_framework.settings import Settings

        assert not any("thinking" in name and name != "conversation_thinking_level"
                       for name in Settings.model_fields)


class TestConversationThinkingIsPerSession:
    """`DIALEXITY_CONVERSATION_THINKING_LEVEL` is the deployment default; a head's
    `thinking=` is the person's own toggle for the session, and `None` there means
    OFF — distinct from not saying, which defers to settings."""

    def _settings(self, di_container, level):
        previous = di_container.settings()
        di_container.settings.override(
            previous.model_copy(update={"conversation_thinking_level": level})
        )
        return previous

    def test_not_given_defers_to_settings(self, di_container):
        previous = self._settings(di_container, "medium")
        try:
            assert ConversationFacilitator()._thinking_kwargs() == {"thinking": "medium"}
        finally:
            di_container.settings.reset_override()
            di_container.settings.override(previous)

    def test_none_is_off_whatever_settings_say(self, di_container):
        previous = self._settings(di_container, "medium")
        try:
            assert ConversationFacilitator(conversation_thinking=None)._thinking_kwargs() == {}
        finally:
            di_container.settings.reset_override()
            di_container.settings.override(previous)

    def test_a_level_wins_over_settings(self, di_container):
        previous = self._settings(di_container, None)
        try:
            assert ConversationFacilitator(conversation_thinking="low")._thinking_kwargs() == {
                "thinking": "low"
            }
        finally:
            di_container.settings.reset_override()
            di_container.settings.override(previous)

    def test_the_toggle_travels_through_isolate(self):
        child = ConversationFacilitator(conversation_thinking="low").isolate(keep_history=False)
        assert child._conversation_thinking == "low"

    def test_every_head_takes_the_toggle(self, di_container):
        """Same shape as `advanced=`: one per-session value, every head."""
        from dialectical_framework.agents.advisor.advisor import Advisor
        from dialectical_framework.agents.analyst.analyst import Analyst

        assert Advisor(thinking=None)._conversation._thinking_kwargs() == {}
        assert Analyst(thinking="low")._conversation._thinking_kwargs() == {"thinking": "low"}
        import inspect

        from dialectical_framework.agents.explorer.explorer import Explorer

        assert "thinking" in inspect.signature(Explorer.__init__).parameters

    def test_the_setting_reads_from_its_new_name(self, monkeypatch):
        from dialectical_framework.settings import Settings

        monkeypatch.setenv("DIALEXITY_CONVERSATION_THINKING_LEVEL", "low")
        assert Settings.from_env().conversation_thinking_level == "low"
        # Empty means unset (the bench relies on `DIALEXITY_CONVERSATION_THINKING_LEVEL=`
        # to run a regime), and the old name is ignored rather than honoured — set
        # to empty rather than deleted, because a local .env may carry a value.
        monkeypatch.setenv("DIALEXITY_CONVERSATION_THINKING_LEVEL", "")
        monkeypatch.setenv("DIALEXITY_THINKING_LEVEL", "medium")  # the old name
        assert Settings.from_env().conversation_thinking_level is None, (
            "no alias: the old environment name must be ignored, not honoured"
        )
