"""
`Advisor.migrate_conversation` — the Consultant → Advisor upgrade.

DB-free: the ingest body, the weave and the seam are patched on the stub, so
what is pinned is WHAT is mined (the person's turns, never the replies), the
ORDER (plant, weave, then the seam per exchange, then the drain), the two
refusals, and what the report says. The seam's own behaviour is pinned in
`tests/test_decision_confirmation_repair.py`.
"""

from __future__ import annotations

import pytest
from mirascope import llm

from dialectical_framework.agents.advisor.advisor import Advisor
from dialectical_framework.agents.advisor.build_policy import BuildPolicy
from dialectical_framework.agents.advisor.migration import (
    MIGRATION_INTENT, MigrationReport, exchanges, message_text, person_turns)
from dialectical_framework.agents.turn_timing import ClosingOutcome
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.scope_context import scope
from test_decision_confirmation_repair import _StubAdvisor


@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


def _history(*turns: tuple[str, str]) -> list:
    """A Consultant-shaped history: system, then (user, assistant) pairs."""
    out: list = [llm.messages.system("the method")]
    for role, text in turns:
        if role == "user":
            out.append(llm.messages.user(text))
        else:
            out.append(llm.messages.assistant(text, model_id=None, provider_id=None))
    return out


class TestWhatIsMined:
    def test_message_text_reads_every_shape(self):
        assert message_text(llm.messages.user("hello")) == "hello"
        assert message_text({"role": "user", "content": "hi"}) == "hi"
        assert message_text({"role": "user", "content": [{"type": "text", "text": "a"}, {"type": "image"}]}) == "a"
        assert message_text(llm.messages.system("s")) == "s"
        assert message_text({"role": "user"}) == ""

    def test_person_turns_are_the_users_words_only(self):
        history = _history(
            ("user", "My cofounder checked out."),
            ("assistant", "That sounds like a tension between loyalty and momentum."),
            ("user", "  "),
            ("user", "I want to buy him out."),
        )
        assert person_turns(history) == ["My cofounder checked out.", "I want to buy him out."]

    def test_exchanges_pair_each_turn_with_its_reply(self):
        history = _history(
            ("assistant", "Hello, what brings you here?"),  # no user turn before it
            ("user", "My cofounder checked out."),
            ("assistant", "A tension between loyalty and momentum."),
            ("user", "Write that down: I buy him out."),  # ended on the person's words
        )
        assert list(exchanges(history)) == [
            ("My cofounder checked out.", "A tension between loyalty and momentum."),
            ("Write that down: I buy him out.", ""),
        ]

    def test_two_user_turns_in_a_row_each_get_an_exchange(self):
        history = _history(("user", "one"), ("user", "two"), ("assistant", "reply"))
        assert list(exchanges(history)) == [("one", ""), ("two", "reply")]


class _MigratingStub(_StubAdvisor):
    """The seam stub plus what the migration reads and binds."""

    migrate_conversation = Advisor.migrate_conversation
    messages = Advisor.__dict__["messages"]

    def __init__(self, history: list, **kwargs) -> None:
        super().__init__([], **kwargs)
        self._conversation._messages = list(history)


class TestTheMigration:
    def _patch(self, monkeypatch, *, closings: dict[str, ClosingOutcome] | None = None):
        """Record the order of the three phases; the seam is a stand-in that
        concludes what `closings` says for each person's message."""
        import dialectical_framework.agents.advisor.tools.ingest as ingest_mod

        log: list = []

        async def fake_ingest(*, text, intent, input_hashes):
            log.append(("ingest", text, intent, input_hashes))
            return '{"artifacts": {"perspective_hashes": ["pp0001", "pp0002"]}}'

        monkeypatch.setattr(ingest_mod, "_ingest", fake_ingest)

        async def fake_weave(self):
            log.append(("weave",))
            return ["tr0001"]

        monkeypatch.setattr(_MigratingStub, "_weave_unwoven_perspectives", fake_weave)

        async def fake_seam(self, user_message, assistant_message):
            log.append(("seam", user_message, assistant_message))
            self._last_closing = (closings or {}).get(user_message, ClosingOutcome.NO_CLOSING)

        monkeypatch.setattr(_MigratingStub, "_repair_unrecorded_decision", fake_seam)

        async def fake_drain(self, timeout=None):
            log.append(("drain",))
            return True

        monkeypatch.setattr(_MigratingStub, "wait_for_deferred_work", fake_drain)
        return log

    async def test_plants_from_the_persons_words_then_weaves_then_runs_the_seam(self, monkeypatch):
        log = self._patch(
            monkeypatch,
            closings={"Write that down: I buy him out.": ClosingOutcome.REPAIRED},
        )
        history = _history(
            ("user", "My cofounder checked out."),
            ("assistant", "A tension between loyalty and momentum."),
            ("user", "Write that down: I buy him out."),
            ("assistant", "Recorded: you buy him out."),
        )
        case = Case()
        case.commit()
        with scope(case.sid):
            report = await _MigratingStub(history).migrate_conversation()

        assert [entry[0] for entry in log] == ["ingest", "weave", "seam", "seam", "drain"]
        ingest = log[0]
        assert ingest[1] == "My cofounder checked out.\n\nWrite that down: I buy him out."
        assert "momentum" not in ingest[1], "the model's reply is never material"
        assert ingest[2] == MIGRATION_INTENT and ingest[3] is None
        assert log[2] == ("seam", "My cofounder checked out.", "A tension between loyalty and momentum.")
        assert log[3] == ("seam", "Write that down: I buy him out.", "Recorded: you buy him out.")
        assert report == MigrationReport(
            turns=2,
            perspectives=["pp0001", "pp0002"],
            pathways=["tr0001"],
            decisions_recorded=1,
            decisions_failed=0,
        )

    async def test_the_turn_fields_are_cleared_afterwards(self, monkeypatch):
        self._patch(monkeypatch, closings={"one": ClosingOutcome.REPAIRED})
        case = Case()
        case.commit()
        with scope(case.sid):
            advisor = _MigratingStub(_history(("user", "one"), ("assistant", "r")))
            await advisor.migrate_conversation()
        assert advisor._last_closing is None and advisor._last_deferral is None

    async def test_a_seam_failure_is_counted_not_raised(self, monkeypatch):
        self._patch(monkeypatch, closings={"one": ClosingOutcome.FAILED})
        case = Case()
        case.commit()
        with scope(case.sid):
            report = await _MigratingStub(_history(("user", "one"), ("assistant", "r"))).migrate_conversation()
        assert report.decisions_failed == 1 and report.decisions_recorded == 0

    async def test_nothing_said_means_nothing_done(self, monkeypatch):
        log = self._patch(monkeypatch)
        case = Case()
        case.commit()
        with scope(case.sid):
            report = await _MigratingStub(_history(("assistant", "Hello?"))).migrate_conversation()
        assert log == [] and report == MigrationReport()

    async def test_needs_a_scope(self, monkeypatch):
        self._patch(monkeypatch)
        with pytest.raises(Exception):
            await _MigratingStub(_history(("user", "one"))).migrate_conversation()

    async def test_refused_on_a_seat_that_may_not_write(self, monkeypatch):
        self._patch(monkeypatch)
        case = Case()
        case.commit()
        with scope(case.sid), pytest.raises(ValueError, match="records=True"):
            await _MigratingStub(_history(("user", "one")), records=False).migrate_conversation()

    async def test_refused_on_a_head_that_never_builds(self, monkeypatch):
        self._patch(monkeypatch)
        case = Case()
        case.commit()
        with scope(case.sid), pytest.raises(ValueError, match="build=NEVER"):
            await _MigratingStub(_history(("user", "one")), build=BuildPolicy.NEVER).migrate_conversation()

    async def test_consent_is_allowed(self, monkeypatch):
        log = self._patch(monkeypatch)
        case = Case()
        case.commit()
        with scope(case.sid):
            await _MigratingStub(_history(("user", "one")), build=BuildPolicy.ON_CONSENT).migrate_conversation()
        assert log[0][0] == "ingest"

    def test_the_real_advisor_binds_it(self):
        assert callable(getattr(Advisor, "migrate_conversation"))
