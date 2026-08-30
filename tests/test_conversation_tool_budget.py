"""
The agentic tool loop stays diagnosable: valid history, and visible outcomes.

Two guarantees, both learned from bench runs that were misread as weak models:
history that survives the round budget (below), and tool outcomes that record
whether a call actually did anything (`TestToolResultRecording`).

--- Part one: history stays API-valid when the loop hits its round budget.

The loop in `submit`/`submit_stream` stops after `max_tool_rounds` even if the
model just asked for another tool. Because `self._messages` is then reassigned
from the response chain, an unanswered `tool_use` does not merely fail one
call — it is PERSISTED and replayed forever after:

    messages.22: `tool_use` ids were found without `tool_result` blocks
    immediately after: toolu_bdrk_01Grxx45A

Observed in the bench as an Advisor session where all six turns failed citing
that same stale id, after ~103 minutes of real tool work whose output was then
unreachable. The turn recorded no text, which reads as "the model collapsed"
rather than "its history was malformed" — the recurring misdiagnosis this
suite exists to prevent (see test_llm_transport_resilience).
"""

from __future__ import annotations

import pytest
from mirascope.llm.content import ToolCall

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.agents.execution_report import ExecutionReport


# DB-free: override the autouse graph fixtures.
@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


class _FakeResponse:
    """Minimal stand-in for the shape `_close_dangling_tool_calls` reads."""

    def __init__(self, tool_calls: list[ToolCall]) -> None:
        self.tool_calls = tool_calls


def _tool_call(id_: str, name: str = "explore") -> ToolCall:
    return ToolCall(id=id_, name=name, args="{}")


def _content_parts(message) -> list:
    content = message.content
    return list(content) if isinstance(content, (list, tuple)) else [content]


class TestDanglingToolCallClosure:
    def test_unanswered_tool_call_gets_a_tool_result(self):
        """The invariant the API enforces: every tool_use is answered."""
        facilitator = ConversationFacilitator(tools=[lambda: None])
        facilitator._close_dangling_tool_calls(
            _FakeResponse([_tool_call("toolu_1")])
        )

        assert len(facilitator._messages) == 1
        last = facilitator._messages[-1]
        assert last.role == "user"
        parts = _content_parts(last)
        assert [p.type for p in parts] == ["tool_output"]
        assert parts[0].id == "toolu_1"

    def test_every_parallel_call_is_answered(self):
        """Anthropic requires ALL ids from one assistant turn answered — a
        partial answer is rejected exactly like no answer."""
        facilitator = ConversationFacilitator(tools=[lambda: None])
        facilitator._close_dangling_tool_calls(
            _FakeResponse(
                [_tool_call("toolu_a", "explore"), _tool_call("toolu_b", "sync")]
            )
        )

        parts = _content_parts(facilitator._messages[-1])
        assert [p.id for p in parts] == ["toolu_a", "toolu_b"]
        assert [p.name for p in parts] == ["explore", "sync"]

    def test_synthetic_result_says_the_tool_did_not_run(self):
        """The model must not read this as a real tool result — otherwise it
        reports invented findings as verified."""
        facilitator = ConversationFacilitator(tools=[lambda: None])
        facilitator._close_dangling_tool_calls(
            _FakeResponse([_tool_call("toolu_1")])
        )

        result = _content_parts(facilitator._messages[-1])[0].result
        assert "not executed" in result.lower()
        assert "do not call more tools" in result.lower()

    def test_no_tool_calls_leaves_history_untouched(self):
        """The overwhelmingly common path: the loop ended because the model was
        done. Appending anything here would corrupt a healthy conversation."""
        facilitator = ConversationFacilitator(tools=[lambda: None])
        facilitator.add_user_message("hello")
        before = list(facilitator._messages)

        facilitator._close_dangling_tool_calls(_FakeResponse([]))

        assert facilitator._messages == before

    def test_history_ends_on_user_so_no_filler_text_is_added(self):
        """`_call_with_response_model` appends its extraction notice
        (`_EXTRACTION_REQUEST`) only when history ends on an assistant turn. The
        closure message must satisfy that check itself, so the extraction sees the
        tool_result as the final turn rather than a text message wedged between
        the tool_use and its answer.

        This path is now the MAIN reason the extraction call still exists:
        `_reuse_written_reply` declines whenever `tool_calls` are still pending,
        which is exactly the overrun this module tests.
        """
        facilitator = ConversationFacilitator(tools=[lambda: None])
        facilitator._close_dangling_tool_calls(
            _FakeResponse([_tool_call("toolu_1")])
        )

        assert facilitator._messages[-1].role == "user"


class TestBudgetExhaustionEndToEnd:
    """Through `submit`, with a model that never stops asking for tools."""

    @pytest.mark.llm
    async def test_persistent_tool_calls_leave_valid_history(self, monkeypatch):
        """The regression itself: a model that always wants another tool must
        not leave a `tool_use` unanswered at the end of history.

        Guards the *persisted* state, not just the immediate call — the bench
        failure was every LATER turn dying on a stale id from this turn.
        """
        from pydantic import BaseModel

        class _Chat(BaseModel):
            message: str

        facilitator = ConversationFacilitator(tools=[lambda: None])
        facilitator.set_system_prompt("You are a test assistant.")

        rounds = {"n": 0}

        class _LoopingResponse:
            """Always asks for one more tool, as a runaway model would."""

            def __init__(self) -> None:
                self.tool_calls = [_tool_call(f"toolu_{rounds['n']}")]
                self.messages = []

            async def execute_tools(self):
                return []

            async def resume(self, _outputs):
                rounds["n"] += 1
                return _LoopingResponse()

        async def _fake_call_with_tools(self):
            return _LoopingResponse()

        monkeypatch.setattr(
            ConversationFacilitator, "_call_with_tools", _fake_call_with_tools
        )

        await facilitator.submit(_Chat, "go", max_tool_rounds=3)

        # Find the last tool_use/tool_output pairing in the persisted history.
        outputs: list[str] = []
        for msg in facilitator._messages:
            for part in _content_parts(msg):
                if getattr(part, "type", None) == "tool_output":
                    outputs.append(part.id)

        assert outputs, "the unanswered tool call was never closed"
        assert f"toolu_{rounds['n']}" in outputs


class TestToolResultRecording:
    """A tool that RAN and reported failure must be distinguishable from one
    that succeeded.

    Same root diagnosis problem, one layer over: `last_tool_calls` records only
    what the model ATTEMPTED. When the bench's A2 arm spent 2.6h issuing
    `anchor` calls against a graph that stayed empty, the recorded JSON showed
    eight attempts, an empty graph, and nothing in between — the failing tool
    was invisible in the data, so the run had to be re-diagnosed by hand.
    """

    def test_report_is_extracted_from_the_real_toolouput_envelope(self):
        """The shape `execute_tools()` actually returns — NOT a bare string.

        A regression that existed from the introduction of streaming: the code
        used `str(output)` on the `ToolOutput` wrapper, which yields the
        dataclass repr (`ToolOutput(type='tool_output', id=..., result='{...}')`).
        Nothing raises — it is a valid string — but it can never parse as an
        ExecutionReport, so every ToolResult event carried report=None and
        consumers saw no graph effects. A test using a bare string would have
        passed against the broken code, which is why this one uses the envelope.
        """
        from mirascope.llm import ToolOutput

        facilitator = ConversationFacilitator(tools=[lambda: None])
        report = ExecutionReport(tool="anchor", ok=True, summary="anchored")
        envelope = ToolOutput(id="toolu_1", name="anchor", result=str(report))

        recorded = facilitator._record_tool_results(
            [_tool_call("toolu_1", name="anchor")], [envelope]
        )

        assert recorded[0].report is not None, "envelope repr leaked instead of result"
        assert recorded[0].report.summary == "anchored"
        assert not recorded[0].raw_output.startswith("ToolOutput(")

    def test_reports_are_paired_with_their_calls(self):
        facilitator = ConversationFacilitator(tools=[lambda: None])
        report = ExecutionReport(tool="anchor", ok=False, summary="dedup failed")

        recorded = facilitator._record_tool_results(
            [_tool_call("toolu_1", name="anchor")], [str(report)]
        )

        assert [r.tool_name for r in recorded] == ["anchor"]
        assert facilitator.last_tool_results == recorded
        assert recorded[0].report is not None
        assert recorded[0].report.ok is False
        assert recorded[0].report.summary == "dedup failed"

    def test_non_report_output_is_kept_with_a_null_report(self):
        """Read-only tools return prose. It must be retained as raw output, not
        dropped and not misparsed into a fake report."""
        facilitator = ConversationFacilitator(tools=[lambda: None])

        recorded = facilitator._record_tool_results(
            [_tool_call("toolu_1", name="sync")], ["here is the graph state"]
        )

        assert recorded[0].report is None
        assert recorded[0].raw_output == "here is the graph state"

    def test_results_accumulate_across_rounds(self):
        facilitator = ConversationFacilitator(tools=[lambda: None])
        facilitator._record_tool_results([_tool_call("t1", name="anchor")], ["a"])
        facilitator._record_tool_results([_tool_call("t2", name="explore")], ["b"])

        assert [r.tool_name for r in facilitator.last_tool_results] == [
            "anchor",
            "explore",
        ]

    def test_extra_output_degrades_to_unknown_rather_than_raising(self):
        """Observability code must never be the reason a turn fails."""
        facilitator = ConversationFacilitator(tools=[lambda: None])

        recorded = facilitator._record_tool_results(
            [_tool_call("toolu_1", name="anchor")], ["a", "orphan"]
        )

        assert [r.tool_name for r in recorded] == ["anchor", "unknown"]

    @pytest.mark.asyncio
    async def test_submit_records_results_and_resets_between_turns(self, monkeypatch):
        """The recording must happen on the non-streaming path too — that is the
        path the bench and every structured caller use."""
        from pydantic import BaseModel

        class _Chat(BaseModel):
            message: str

        facilitator = ConversationFacilitator(tools=[lambda: None])
        facilitator.set_system_prompt("You are a test assistant.")

        report = ExecutionReport(tool="anchor", ok=False, summary="boom")
        state = {"served": False}

        class _OneToolResponse:
            def __init__(self, tool_calls) -> None:
                self.tool_calls = tool_calls
                self.messages = []

            async def execute_tools(self):
                return [str(report)]

            async def resume(self, _outputs):
                return _OneToolResponse([])

        async def _fake_call_with_tools(self):
            state["served"] = True
            return _OneToolResponse([_tool_call("toolu_1", name="anchor")])

        monkeypatch.setattr(
            ConversationFacilitator, "_call_with_tools", _fake_call_with_tools
        )

        await facilitator.submit(_Chat, "go", max_tool_rounds=3)
        assert state["served"]
        assert [r.tool_name for r in facilitator.last_tool_results] == ["anchor"]
        assert facilitator.last_tool_results[0].report.ok is False

        # A second turn must report ITS own tools, not the previous turn's —
        # otherwise a stale failure would be attributed to a healthy turn.
        async def _no_tools(self):
            return _OneToolResponse([])

        monkeypatch.setattr(ConversationFacilitator, "_call_with_tools", _no_tools)
        await facilitator.submit(_Chat, "again", max_tool_rounds=3)
        assert facilitator.last_tool_results == []


class TestRaisedToolIsVisible:
    """A tool that THREW must not be filed as a tool that returned prose.

    Mirascope catches the exception inside `Tool.execute` and hands back
    `ToolOutput(result=str(e), error=ToolExecutionError(e))`. The exception
    therefore never crosses back into `src/`, so the framework's own
    `except: logger.exception(...)` discipline does not apply and NOTHING logged
    it. The recorded outcome was `report=None` — identical to what `sync` or
    `inspect_node` produce — so a crashed `anchor` appeared in the record as a
    call with no outcome at all.

    Measured in `claim2-weak-r11`: three A2 `anchor` calls with no recorded
    outcome, one of them in the only cell whose graph stayed at
    `perspectives=0`. The turn read as a healthy reply over an empty graph,
    which is the exact misdiagnosis shape ("the model declined to use its
    tools") that the rest of this suite exists to prevent.
    """

    def test_the_error_is_recorded_on_the_result(self):
        from mirascope.llm import ToolOutput
        from mirascope.llm.exceptions import ToolExecutionError

        facilitator = ConversationFacilitator(tools=[lambda: None])
        cause = RuntimeError("Failed to acquire connection")
        envelope = ToolOutput(
            id="toolu_1",
            name="anchor",
            result=str(cause),
            error=ToolExecutionError(cause),
        )

        recorded = facilitator._record_tool_results(
            [_tool_call("toolu_1", name="anchor")], [envelope]
        )

        assert recorded[0].error is not None
        assert "Failed to acquire connection" in recorded[0].error
        # The report stays None (the output was never a report) — `error` is what
        # distinguishes this from a read-only tool, so both must be checked.
        assert recorded[0].report is None

    def test_a_healthy_result_carries_no_error(self):
        """The overwhelmingly common path. A truthy `error` here would make every
        successful call read as a crash."""
        from mirascope.llm import ToolOutput

        facilitator = ConversationFacilitator(tools=[lambda: None])
        report = ExecutionReport(tool="anchor", ok=True, summary="anchored")
        envelope = ToolOutput(id="toolu_1", name="anchor", result=str(report))

        recorded = facilitator._record_tool_results(
            [_tool_call("toolu_1", name="anchor")], [envelope]
        )

        assert recorded[0].error is None

    def test_the_raise_is_logged_at_error(self, caplog):
        """The bench's swallowed-error capture listens on the
        `dialectical_framework` logger at ERROR. Without this log line a raised
        tool leaves no trace anywhere outside the returned dataclass, so a run
        saved before this fix cannot be diagnosed at all."""
        import logging

        from mirascope.llm import ToolOutput
        from mirascope.llm.exceptions import ToolExecutionError

        facilitator = ConversationFacilitator(tools=[lambda: None])
        envelope = ToolOutput(
            id="toolu_1",
            name="anchor",
            result="pool exhausted",
            error=ToolExecutionError(RuntimeError("pool exhausted")),
        )

        with caplog.at_level(logging.ERROR, logger="dialectical_framework"):
            facilitator._record_tool_results(
                [_tool_call("toolu_1", name="anchor")], [envelope]
            )

        raised = [
            r
            for r in caplog.records
            if r.levelno >= logging.ERROR and "anchor" in r.getMessage()
        ]
        assert raised, "a raised tool left no ERROR-level trace"
        # The cause must be in the line, not just the tool name — the whole point
        # is that the run can be diagnosed from the log alone.
        assert "pool exhausted" in raised[0].getMessage()

    def test_a_plain_string_output_is_still_accepted(self):
        """`_record_tool_results` is also called with bare strings in tests and
        by any caller that pre-extracts the result. `getattr(output, "error")`
        must degrade, not raise."""
        facilitator = ConversationFacilitator(tools=[lambda: None])

        recorded = facilitator._record_tool_results(
            [_tool_call("toolu_1", name="sync")], ["here is the graph state"]
        )

        assert recorded[0].error is None
        assert recorded[0].raw_output == "here is the graph state"


class TestToolCallArgsAreRecorded:
    """Whether an OPTIONAL parameter was filled is its own question.

    Names say what was called, reports say whether it worked, and neither can
    answer "did the model pass `context`?" — which for `anchor` is the whole
    difference between a prompt defect and a framework one, because `context` is
    the only carrier of the person's particulars into the next session. Measured
    in `r12-raise-probe`: two `anchor:ok` calls, two perspectives, and ZERO
    grounding lines in the carryover, with no way to tell from the record which
    side dropped them.
    """

    def test_args_are_parsed_alongside_the_names(self):
        facilitator = ConversationFacilitator(tools=[lambda: None])
        call = ToolCall(id="t1", name="anchor", args='{"thesis": "buy him out"}')

        facilitator._record_tool_call_args([call])

        assert facilitator.last_tool_call_args == [{"thesis": "buy him out"}]

    def test_the_lists_stay_index_aligned(self):
        """Consumers zip names against args, so a skipped entry would misattribute
        one call's arguments to another call."""
        facilitator = ConversationFacilitator(tools=[lambda: None])

        facilitator._record_tool_call_args(
            [
                ToolCall(id="t1", name="anchor", args='{"context": "45% split"}'),
                ToolCall(id="t2", name="sync", args=""),
            ]
        )

        assert facilitator.last_tool_call_args == [{"context": "45% split"}, {}]

    def test_unparseable_args_record_empty_rather_than_raising(self):
        """This exists only to make a run diagnosable — it must never be the
        reason a turn fails."""
        facilitator = ConversationFacilitator(tools=[lambda: None])

        facilitator._record_tool_call_args(
            [ToolCall(id="t1", name="anchor", args="{not json")]
        )

        assert facilitator.last_tool_call_args == [{}]

    def test_non_object_args_record_empty(self):
        """Valid JSON that is not an object would break `.get()` downstream."""
        facilitator = ConversationFacilitator(tools=[lambda: None])

        facilitator._record_tool_call_args(
            [ToolCall(id="t1", name="anchor", args="[1, 2]")]
        )

        assert facilitator.last_tool_call_args == [{}]

    @pytest.mark.asyncio
    async def test_streaming_resets_results_between_turns(self, monkeypatch):
        """`submit` reset `last_tool_results`; `submit_stream` did not. A turn
        inheriting the previous turn's outcomes attributes a crash to a healthy
        turn AND leaves the healthy turn's own tools looking unreported — the
        same misdiagnosis this whole suite guards.
        """
        from pydantic import BaseModel

        class _Chat(BaseModel):
            message: str

        facilitator = ConversationFacilitator(tools=[lambda: None])
        facilitator.set_system_prompt("You are a test assistant.")

        # Stale state from an earlier turn.
        facilitator._record_tool_results([_tool_call("old", name="anchor")], ["x"])
        facilitator._record_tool_call_args(
            [ToolCall(id="old", name="anchor", args="{}")]
        )
        assert facilitator.last_tool_results

        class _NoToolStream:
            def __init__(self) -> None:
                self.tool_calls = []
                self.messages = []

            async def chunk_stream(self):
                return
                yield  # pragma: no cover - makes this an async generator

        async def _fake_open(self, max_attempts: int = 3):
            return _NoToolStream()

        monkeypatch.setattr(
            ConversationFacilitator, "_open_stream_with_retry", _fake_open
        )

        async for _ in facilitator.submit_stream(_Chat, "go", max_tool_rounds=3):
            pass

        assert facilitator.last_tool_results == []
        assert facilitator.last_tool_call_args == []
