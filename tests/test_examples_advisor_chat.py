"""`examples/advisor_chat.py` is a claim about the API, so it gets a test.

An example is documentation that can go stale silently: rename a stream event,
change a constructor keyword, and the file people copy first stops running while
every other test stays green. These tests drive the example end to end with the
provider and the graph replaced by stand-ins, so a rename that breaks it fails
here instead of in an integrator's terminal.

They deliberately assert the FIVE HOST OBLIGATIONS the example exists to
demonstrate (docs/agents.md), not its prose: DI setup runs once, every turn is
scoped, the conversation is carried forward, the generator is closed, and
deferred work is drained at the end. If one of those stops being exercised the
example has lost its point even if it still imports.
"""

from __future__ import annotations

import builtins
import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pytest

from dialectical_framework.agents.stream_events import (
    ResponseComplete,
    TextDelta,
    ToolResult,
    ToolStart,
)

EXAMPLE_PATH = Path(__file__).resolve().parent.parent / "examples" / "advisor_chat.py"


@pytest.fixture(scope="module")
def example():
    """The example, imported by path.

    By path because `examples/` is not a package and must not become one just to
    be testable — it is a directory of files people read and run directly.
    """
    spec = importlib.util.spec_from_file_location("_example_advisor_chat", EXAMPLE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@dataclass
class _Reply:
    message: str


class _FakeStream:
    """An async generator stand-in that records whether it was CLOSED.

    A real async generator's cleanup runs on close, not when the consumer walks
    away, so "did the host close it" is the property the `aclosing` obligation is
    about — and the only way to see it is to be the generator.
    """

    def __init__(self, events):
        self._events = list(events)
        self.closed = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._events:
            raise StopAsyncIteration
        return self._events.pop(0)

    async def aclose(self):
        self.closed = True


class _FakeAdvisor:
    """Records what the host did to it. Constructed exactly like the real one."""

    instances: list["_FakeAdvisor"] = []

    def __init__(
        self,
        app_preamble: Optional[str] = None,
        messages: Optional[list] = None,
        principal: str = "unattested",
        **kwargs,
    ):
        self.app_preamble = app_preamble
        self.received_messages = list(messages) if messages else []
        self.principal = principal
        self.prompts: list[str] = []
        self.streams: list[_FakeStream] = []
        self.drained_with: list[float | None] = []
        self.scope_during_turn: list[str | None] = []
        _FakeAdvisor.instances.append(self)

    def chat_stream(self, user_message: str):
        from dialectical_framework.graph.scope_context import get_current_sid

        self.prompts.append(user_message)
        self.scope_during_turn.append(get_current_sid())
        stream = _FakeStream(
            [
                TextDelta(text="Two things "),
                TextDelta(text="pull at once."),
                ResponseComplete(
                    result=_Reply("Two things pull at once."), streamed=True
                ),
            ]
        )
        self.streams.append(stream)
        return stream

    @property
    def messages(self) -> list:
        # Whatever came in, plus a marker for this turn — so the assertion can
        # name which turns the next instance was handed, not just how many.
        return [*self.received_messages, *(f"said:{p}" for p in self.prompts)]

    async def wait_for_deferred_work(self, timeout: float | None = None) -> bool:
        self.drained_with.append(timeout)
        return True


class _FakeCase:
    committed = 0

    def __init__(self):
        self.sid = "sid-example"

    def commit(self):
        _FakeCase.committed += 1


@pytest.fixture
def driven(example, monkeypatch):
    """The example, wired to stand-ins, ready to run with scripted input."""
    _FakeAdvisor.instances = []
    _FakeCase.committed = 0
    setup_calls: list[object] = []

    monkeypatch.setattr(
        example.DialecticalReasoning,
        "setup",
        staticmethod(lambda settings: setup_calls.append(settings)),
    )
    monkeypatch.setattr(example.Settings, "from_env", staticmethod(lambda: "settings"))
    monkeypatch.setattr(example, "Case", _FakeCase)
    monkeypatch.setattr(example, "Advisor", _FakeAdvisor)

    def run(lines: list[str], argv: list[str] | None = None):
        typed = list(lines)

        def fake_input(prompt: str = "") -> str:
            if not typed:
                raise EOFError
            return typed.pop(0)

        # `to_thread` so the example does not block the loop on `input`; the test
        # only needs the value, and a thread hop would make failures async.
        async def fake_to_thread(fn, *a, **kw):
            return fn(*a, **kw)

        monkeypatch.setattr(builtins, "input", fake_input)
        monkeypatch.setattr(example.asyncio, "to_thread", fake_to_thread)
        monkeypatch.setattr(sys, "argv", ["advisor_chat.py", *(argv or [])])
        return setup_calls

    run.setup_calls = setup_calls
    return example, run


class TestTheFiveObligations:
    async def test_di_is_set_up_once_before_anything_else(self, driven):
        example, run = driven
        calls = run([])
        await example.main()
        assert calls == ["settings"], (
            "Obligation 1: the example must call "
            "DialecticalReasoning.setup(Settings.from_env()) exactly once."
        )

    async def test_a_fresh_case_owns_the_sid(self, driven):
        example, run = driven
        run([])
        await example.main()
        assert _FakeCase.committed == 1, "an uncommitted Case owns no sid"

    async def test_an_existing_sid_is_reused_instead_of_making_a_case(self, driven):
        example, run = driven
        run(["What now?", "/quit"], argv=["--sid", "sid-resumed"])
        await example.main()
        assert _FakeCase.committed == 0, "--sid must not create a second Case"
        assert _FakeAdvisor.instances[0].scope_during_turn == ["sid-resumed"]

    async def test_every_turn_runs_inside_the_scope(self, driven):
        example, run = driven
        run(["First", "Second", "/quit"])
        await example.main()
        turns = [sid for a in _FakeAdvisor.instances for sid in a.scope_during_turn]
        assert turns == ["sid-example", "sid-example"], (
            "Obligation 2: an unscoped turn raises MissingScopeError, so every "
            "chat_stream has to see the sid."
        )

    async def test_the_conversation_is_carried_forward(self, driven):
        example, run = driven
        run(["First", "Second", "Third", "/quit"])
        await example.main()
        received = [a.received_messages for a in _FakeAdvisor.instances]
        assert received == [
            [],
            ["said:First"],
            ["said:First", "said:Second"],
        ], (
            "Obligation 3: each turn must be handed the messages the previous "
            "turn ended with, or the Advisor starts over every time."
        )

    async def test_the_generator_is_closed(self, driven):
        example, run = driven
        run(["First", "/quit"])
        await example.main()
        streams = [s for a in _FakeAdvisor.instances for s in a.streams]
        assert streams and all(s.closed for s in streams), (
            "aclosing obligation: an unclosed generator holds the provider "
            "connection open and loses the turn's recorded seconds."
        )

    async def test_deferred_work_is_drained_once_at_the_end(self, driven):
        example, run = driven
        run(["First", "Second", "/quit"])
        await example.main()
        drains = [t for a in _FakeAdvisor.instances for t in a.drained_with]
        assert (
            len(drains) == 1
        ), "Obligation 5: drain once after the LAST turn, not per turn."
        assert drains[0] is not None, "a shutdown path must not hang unbounded"
        # The last instance holds the drain, and that is the point: deferred work
        # is keyed by sid, so whichever instance the host happens to have works.
        assert _FakeAdvisor.instances[-1].drained_with == drains

    async def test_quitting_before_the_first_turn_does_not_crash(self, driven):
        example, run = driven
        run(["/quit"])
        await example.main()  # no Advisor exists to drain — must not raise
        assert _FakeAdvisor.instances == []

    async def test_end_of_input_ends_the_conversation(self, driven):
        example, run = driven
        run(["First"])  # no /quit: input runs out, raising EOFError
        await example.main()
        assert len(_FakeAdvisor.instances) == 1
        assert _FakeAdvisor.instances[0].drained_with == [120]

    async def test_blank_lines_are_not_turns(self, driven):
        example, run = driven
        run(["", "   ", "Real question", "/quit"])
        await example.main()
        assert (
            len(_FakeAdvisor.instances) == 1
        ), "a blank line must not spend a provider call"


class TestRendering:
    """The example's own claims about the stream contract."""

    async def test_streamed_text_is_printed_once(self, example, capsys):
        advisor = _FakeAdvisor()
        await example.run_turn(advisor, "Anything")
        out = capsys.readouterr().out
        assert out.count("Two things pull at once.") == 1, (
            "streamed=True means `message` is the deltas already printed — "
            "printing it again would double the reply on screen."
        )

    async def test_an_unstreamed_reply_is_printed(self, example, capsys):
        class _Unstreamed(_FakeAdvisor):
            def chat_stream(self, user_message: str):
                stream = _FakeStream(
                    [
                        ResponseComplete(
                            result=_Reply("The durable reply."), streamed=False
                        )
                    ]
                )
                self.streams.append(stream)
                return stream

        await example.run_turn(_Unstreamed(), "Anything")
        assert "The durable reply." in capsys.readouterr().out, (
            "streamed=False means nothing was shown yet and `message` is the "
            "only copy of the reply."
        )

    async def test_a_failed_tool_is_visible(self, example, capsys):
        class _Failing(_FakeAdvisor):
            def chat_stream(self, user_message: str):
                stream = _FakeStream(
                    [
                        ToolStart(tool_name="analyze", tool_args={}),
                        ToolResult(
                            tool_name="analyze",
                            report=None,
                            raw_output="boom",
                            error="boom",
                        ),
                        ResponseComplete(result=_Reply("Sorry."), streamed=False),
                    ]
                )
                self.streams.append(stream)
                return stream

        await example.run_turn(_Failing(), "Anything")
        out = capsys.readouterr().out
        assert "analyze failed: boom" in out, (
            "Mirascope returns a raised tool's str(e) as the result, so a host "
            "that ignores `error` cannot tell a crash from prose."
        )


class TestTheReadmeSnippet:
    """The README's Integration snippet is the first code anyone runs.

    It cannot be executed here (it needs a provider and a graph), so these tests
    check the two ways it rots without anyone noticing: it stops being valid
    Python, or it names something the framework no longer exports.
    """

    @staticmethod
    def _snippet() -> str:
        readme = (Path(__file__).resolve().parent.parent / "README.md").read_text()
        blocks = readme.split("```python")
        assert len(blocks) >= 2, "the README lost its python example"
        return blocks[1].split("```")[0]

    def test_it_is_valid_python(self):
        compile(self._snippet(), "README.md", "exec")

    def test_it_is_self_contained(self):
        snippet = self._snippet()
        # A fragment that calls an undefined helper reads as runnable and is not.
        assert (
            "asyncio.run(" in snippet
        ), "an `await` outside `asyncio.run` cannot be pasted into a file and run"

    def test_every_name_it_imports_exists(self):
        import importlib

        for line in self._snippet().splitlines():
            line = line.strip()
            if not line.startswith("from dialectical_framework"):
                continue
            module_path, _, names = line.partition(" import ")
            module = importlib.import_module(module_path[len("from ") :])
            for name in (n.strip() for n in names.split(",")):
                assert hasattr(module, name), (
                    f"README imports {name} from {module_path[len('from '):]}, "
                    "which no longer has it"
                )

    def test_the_methods_it_calls_exist(self):
        from dialectical_framework.agents.advisor.advisor import Advisor

        for method in ("chat_stream", "wait_for_deferred_work"):
            assert hasattr(Advisor, method), f"README calls Advisor.{method}"
