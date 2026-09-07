"""`record_decision` must speak during its one silent stretch, and only that one.

WHY THIS TEST EXISTS
====================
`record_decision` is the shortest of the instrumented stages and the one where
silence costs the most. Everything the concern does is bookkeeping the person can
already see: validation refuses in-band with a reason in the report, and the graph
writes publish `node_created`/`node_updated` effects on the `sid` channel as they
land. Exactly one stretch produces nothing until it returns — the coherence
review, measured at ~5.6s by `probe_first_delta.py` — and it happens on the one
path whose entire contract is that the person just said yes and is waiting to see
their decision recorded.

So the accounting here is deliberately ONE step, and the risk this file guards is
the opposite of `ingest`'s. There, the danger was a denominator spread over three
modules that could not be checked by grep. Here the danger is drift toward
narrating the writes — a second `expect_progress` for "writing it down" would
duplicate an effect the host already received for the same commit, and a host
showing both would tell the person their decision was saved twice.

The refusal path gets its own test because its honest closing event is `0/0`:
nothing was done, and the reason travels in the report, not in a progress label.
That is why `_assert_accounting_closes` in `tests/test_ingest_progress.py` does
NOT transfer here — its `assert steps` vacuity guard would fail this branch for
behaving correctly.

Mock brain throughout: this is about the accounting, not the verdict.

Run: poetry run pytest tests/test_decision_progress.py
"""

from __future__ import annotations

import asyncio
import json

import pytest

from dialectical_framework.agents.advisor.tools.record_decision import (
    _progress_key, record_decision)
from dialectical_framework.events.graph_event_bus import GraphEventBus
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.repositories.decision_repository import (
    DecisionRepository,
)
from dialectical_framework.graph.scope_context import scope
from dialectical_framework.utils import progress as progress_module

QUESTION = "Which job offer to take?"
STANCE = "Accept the startup offer"
RATIONALE = "Growth outweighs the stability I am giving up."

#: Terms a host may not render to a person under the silent Advisor. Detail
#: strings are the one part of this seam written FOR a human, and
#: `utils/progress.py` warns a host may show them verbatim.
BANNED = (
    "thesis",
    "antithesis",
    "polarity",
    "tetrad",
    "perspective",
    "nexus",
    "wheel",
    "dialectical",
    "framework",
    "synthesis",
    "digest",
    "coherence",
)


def _new_sid() -> str:
    case = Case()
    case.commit()
    assert case.sid is not None
    return case.sid


@pytest.fixture
async def collected_progress():
    """Subscribe to `sid:progress` and hand back the bus for one run."""
    bus = GraphEventBus()
    await bus.connect()
    # RESTORE, never clear: the module-level bus is wired once by the
    # session-scoped `di_container` fixture, so `None` here would silently
    # disable progress for every test that ran afterwards.
    previous = progress_module._event_bus
    progress_module.set_event_bus(bus)
    try:
        yield bus
    finally:
        progress_module.set_event_bus(previous)
        await bus.disconnect()


async def _record_collecting(bus, sid: str, **kwargs) -> tuple[dict, list]:
    """Run `record_decision` under `sid` while draining its progress channel.

    The `scope` is entered around the AWAIT, not around building the coroutine:
    `_publish` drops every event when no sid is in scope, so a factory that left
    the `with` block before anything ran would report "the person saw silence"
    about the harness rather than about the tool.
    """
    received: list = []
    ready = asyncio.Event()

    async def _listen() -> None:
        async with bus.subscribe_progress(sid) as subscriber:
            ready.set()
            async for event in subscriber:
                received.append(event.message)

    listener = asyncio.create_task(_listen())
    await ready.wait()
    try:
        with scope(sid):
            result = await record_decision(**kwargs)
        await _drain(received)
    finally:
        listener.cancel()
    return json.loads(result), received


async def _drain(received: list, *, timeout: float = 5.0) -> None:
    """Wait until `received` stops growing (mirrors `test_ingest_progress.py`).

    Not a fixed sleep: publishes are fire-and-forget `create_task`s, and a fixed
    interval passes on an idle machine while dropping the closing event under
    load — which reads as a missing `final` rather than as flake.
    """
    previous = -1
    waited = 0.0
    while previous != len(received) and waited < timeout:
        previous = len(received)
        await asyncio.sleep(0.05)
        waited += 0.05


def _closing_event(events: list, *, branch: str):
    assert events, f"{branch}: not one progress event — the person saw silence"
    finals = [e for e in events if e.final]
    assert len(finals) == 1, (
        f"{branch}: expected exactly one closing event, got {len(finals)} —"
        " a host clears its indicator on `final`"
    )
    assert finals[0].stage == "decision"
    # One non-None key shared by every event of the run. `execute_tools()` runs a
    # tool round concurrently, so the key is the only thing that lets a host tell
    # two streams on the same sid and stage apart.
    keys = {e.key for e in events}
    assert keys != {None}, f"{branch}: progress published with no key"
    assert len(keys) == 1, f"{branch}: one run published several keys: {keys}"
    return finals[0]


@pytest.mark.llm
@pytest.mark.asyncio
class TestRecordingSpeaksExactlyOnce:
    async def test_the_quiet_stretch_is_labelled_and_the_total_closes(
        self, collected_progress
    ):
        """One step declared, one step reported, closing at 1/1.

        The step count is the claim. Two would mean a write got narrated on the
        progress channel as well as on the effect channel; zero would mean the
        ~5.6s wait went by unannounced on the one call where the person is
        watching for their decision to land.
        """
        from test_dialectical_context import _create_perspective_with_aspects

        sid = _new_sid()
        with scope(sid):
            ground, _ = _create_perspective_with_aspects().t_minus.get()
            ground_hash = ground.hash

        report, events = await _record_collecting(
            collected_progress,
            sid,
            question=QUESTION,
            stance=STANCE,
            rationale=RATIONALE,
            grounds=[{"hash": ground_hash, "role": "accepted_cost"}],
        )
        assert report["ok"] is True, report["summary"]

        final = _closing_event(events, branch="recorded")
        steps = [e for e in events if not e.final]

        assert len(steps) == 1, (
            "expected exactly one announced step, got"
            f" {[e.detail for e in steps]} — the writes already reach the host as"
            " effects on the `sid` channel, so a second progress step tells the"
            " person the same commit happened twice"
        )
        assert final.done == final.total == 1, (
            f"closed at {final.done}/{final.total} — the declared total and what"
            " was reported disagree, so a host's bar either sticks or overshoots"
        )
        assert steps[0].done == 0 and steps[0].total == 1

    async def test_the_label_says_what_is_happening_without_naming_machinery(
        self, collected_progress
    ):
        """The detail is written for a person, and a host may render it verbatim."""
        from test_dialectical_context import _create_perspective_with_aspects

        sid = _new_sid()
        with scope(sid):
            ground, _ = _create_perspective_with_aspects().t_minus.get()
            ground_hash = ground.hash

        _report, events = await _record_collecting(
            collected_progress,
            sid,
            question=QUESTION,
            stance=STANCE,
            rationale=RATIONALE,
            grounds=[{"hash": ground_hash, "role": "accepted_cost"}],
        )
        details = [e.detail for e in events if not e.final and e.detail]
        assert details, "no detail to check — the assertions below would be vacuous"

        for detail in details:
            lowered = detail.lower()
            for term in BANNED:
                assert term not in lowered, (
                    f"progress detail {detail!r} names the machinery ({term!r}) —"
                    " a host renders this to a person who never asked for the"
                    " framework's vocabulary"
                )

    async def test_no_label_quotes_the_confirmed_decision(self, collected_progress):
        """The person's confirmed wording is the most sensitive text on this path.

        It is what they just committed to, in their own words, and a host may put a
        progress detail in a title bar or a notification. Nothing about the
        question, the stance or the rationale may travel on this channel — the
        report is where the decision's text belongs.
        """
        from test_dialectical_context import _create_perspective_with_aspects

        fingerprint = "leaving Ravensbourne for the Helsinki startup"

        sid = _new_sid()
        with scope(sid):
            ground, _ = _create_perspective_with_aspects().t_minus.get()
            ground_hash = ground.hash

        _report, events = await _record_collecting(
            collected_progress,
            sid,
            question=f"Should I take the offer, {fingerprint}?",
            stance=f"Yes, {fingerprint}",
            rationale=f"The growth is worth {fingerprint}.",
            grounds=[{"hash": ground_hash, "role": "accepted_cost"}],
        )
        # Without this the loop below passes on an empty stream, which is the one
        # failure mode a leak test cannot afford to be blind to.
        assert events, "no progress at all — the assertions below would be vacuous"

        for event in events:
            for field in (event.detail, event.key):
                if not field:
                    continue
                assert fingerprint.lower() not in field.lower(), (
                    f"{field!r} carries the person's own confirmed wording onto the"
                    " progress channel"
                )
                assert len(field) < 200, (
                    f"{field!r} is long enough to be carrying their text rather"
                    " than describing the work"
                )


@pytest.mark.llm
@pytest.mark.asyncio
class TestAnInBandRefusalClosesAtZero:
    async def test_a_refused_call_declares_nothing_and_says_so(
        self, collected_progress
    ):
        """`0/0` is the honest report when the concern never got to the quiet part.

        Validation refuses before step 5, so no site declares a step. A host must
        still receive the closing event — otherwise its indicator spins forever on
        a call that already failed — and it must not be told that 0 of 1 things
        were done, which reads as work in flight.
        """
        sid = _new_sid()
        report, events = await _record_collecting(
            collected_progress,
            sid,
            question=QUESTION,
            stance=STANCE,
            rationale=RATIONALE,
            grounds=[{"hash": "nonexistent"}],
        )
        assert report["ok"] is False
        with scope(sid):
            assert DecisionRepository().find_all() == []

        final = _closing_event(events, branch="refused")
        assert [e for e in events if not e.final] == [], (
            "a refused call announced a step — nothing was done, and the reason"
            " belongs in the report, not on the progress channel"
        )
        assert final.done == 0 and final.total == 0, (
            f"refusal closed at {final.done}/{final.total} — a declared step that"
            " never ran is indistinguishable from one that failed"
        )


class TestTheProgressKeySeparatesConcurrentRecordings:
    """DB-free: `_progress_key` is a pure function of the confirmed wording.

    Racing two real recordings would also race two graph write sequences through
    GQLAlchemy, which is not concurrency-safe (CLAUDE.md) — any flake that produced
    would be blamed on progress. The single-run tests above already assert the key
    reaches the events.
    """

    @pytest.fixture(autouse=True)
    def cleanup_graph_db(self):
        yield

    @pytest.fixture(autouse=True)
    def cleanup_test_graph_data(self):
        yield

    def test_the_same_call_retried_keeps_its_key(self):
        assert _progress_key(QUESTION, STANCE) == _progress_key(QUESTION, STANCE)

    def test_two_decisions_in_one_round_get_different_keys(self):
        assert _progress_key(QUESTION, STANCE) != _progress_key(
            QUESTION, "Stay where I am"
        )
        assert _progress_key(QUESTION, STANCE) != _progress_key(
            "Which house to buy?", STANCE
        )

    def test_the_key_is_opaque(self):
        """Hashed on purpose: a host may render the key as a label.

        If it were the confirmed wording, that label would quote the decision the
        person just made back at them from a progress bar.
        """
        key = _progress_key("Should I leave Ravensbourne?", "Yes, take the offer")
        assert len(key) == 10
        assert all(c in "0123456789abcdef" for c in key)
        for word in ("Ravensbourne", "leave", "offer", "Yes"):
            assert word.lower() not in key
