"""
Structured calls can think — but only in JSON formatting mode.

Every concern DTO reaches the provider through
`ConversationFacilitator._call_with_response_model`, whose default formatting
mode is forced tool use, and the provider rejects extended thinking on that
shape ("Thinking may not be enabled when tool_choice forces tool use"). So the
framework's own reasoning has never thought, whatever `thinking_level` said —
that setting reaches only the conversational tool path.

`ConversationFacilitator(format_mode="json", thinking=...)` is the door:
Mirascope's JSON mode parses a DTO-shaped call 4/4 with less prefill than tool
mode and accepts thinking (`tests/e2e/probe_format_mode_thinking.py`).
`ThesisExtraction` opts in through `settings.extraction_thinking_level`. These
tests pin the plumbing DB-free: what reaches `use_brain`, that the shape
travels through `isolate()`, that the impossible combination is refused at
construction, and that the setting reaches the concern.
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


class TestTheExtractionConcernOptsInThroughSettings:
    def test_unset_means_the_default_shape(self, di_container):
        from dialectical_framework.concerns.thesis_extraction import \
            ThesisExtraction

        concern = ThesisExtraction()
        assert concern._conversation._format_mode is None
        assert concern._conversation._structured_thinking is None

    def test_a_level_switches_the_concern_to_json_mode_with_thinking(
        self, di_container
    ):
        from dialectical_framework.concerns.thesis_extraction import \
            ThesisExtraction

        previous = di_container.settings()
        di_container.settings.override(
            previous.model_copy(update={"extraction_thinking_level": "medium"})
        )
        try:
            concern = ThesisExtraction()
        finally:
            di_container.settings.reset_override()
            di_container.settings.override(previous)
        assert concern._conversation._format_mode == "json"
        assert concern._conversation._structured_thinking == "medium"
        # And the step-2 fan-out inherits it.
        assert concern._conversation.isolate()._structured_thinking == "medium"

    def test_the_setting_reads_from_the_environment(self, monkeypatch):
        from dialectical_framework.settings import Settings

        assert Settings.model_fields["extraction_thinking_level"].default is None
        monkeypatch.setenv("DIALEXITY_EXTRACTION_THINKING_LEVEL", "low")
        assert Settings.from_env().extraction_thinking_level == "low"
        monkeypatch.setenv("DIALEXITY_EXTRACTION_THINKING_LEVEL", "")
        assert Settings.from_env().extraction_thinking_level is None
