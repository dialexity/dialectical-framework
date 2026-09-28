"""
The off-turn seam on a shared, multi-tenant server (2026-09-28).

Two defects a review against that deployment found, and what closes each:

1. One writer per sid was enforced by an in-process dict. With several worker
   processes or replicas, two turns of one conversation land on different
   ones; worker B found no task, waited nothing, and its closing started a
   second weave on the sid worker A was weaving. Now the task takes a DB-held
   lease per sid (`CaseRepository.acquire_weave_lease`, compare-and-set in one
   statement), renews it per round, releases it when done — and every turn
   waits out a lease another process holds (`_wait_for_foreign_weave`).

2. Notes lived in RAM, and the model told the person "written down" on the
   strength of that. A deploy between the reply and the plant lost the note.
   Now `_queue_note` commits a `Note` node before it returns, and the drain
   reads unplanted notes back from the graph — in whichever process runs it.

Plus the server-side drain (`drain_deferred_work`) a lifespan shutdown hook
can call without a scope or an instance.

Real Memgraph; the anchor body and the weave are patched so no provider is
called. "Another process" is simulated by holding the lease under a foreign
owner string and by dropping this process's registry entry.
"""

from __future__ import annotations

import asyncio
import time

import pytest

import dialectical_framework.agents.advisor.advisor as advisor_mod
import dialectical_framework.agents.advisor.tools.anchor as anchor_mod
import dialectical_framework.agents.advisor.tools.explore as explore_mod
from dialectical_framework.agents.advisor.advisor import (
    _DEFERRED_WORK, Advisor, deferred_work_in_flight, drain_deferred_work)
from dialectical_framework.agents.advisor.build_policy import BuildPolicy
from dialectical_framework.agents.turn_timing import DeferralOutcome
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.note import Note
from dialectical_framework.graph.repositories.case_repository import \
    CaseRepository
from dialectical_framework.graph.repositories.nexus_repository import \
    NexusRepository
from dialectical_framework.graph.repositories.note_repository import \
    NoteRepository
from dialectical_framework.graph.scope_context import scope

#: A lease holder that is not this process.
OTHER_PROCESS = "other-host:4242:feedface"


def _case() -> Case:
    case = Case()
    case.commit()
    return case


def _fake_anchor(monkeypatch, *, block: asyncio.Event | None = None) -> list[dict]:
    """`anchor`'s body replaced: records the call, optionally blocks, returns a
    report naming one perspective."""
    calls: list[dict] = []

    async def fake(*, thesis, antithesis, context):
        if block is not None:
            await block.wait()
        calls.append({"thesis": thesis, "antithesis": antithesis, "context": context})
        return '{"artifacts": {"perspective_hashes": ["pp%04d"]}}' % len(calls)

    monkeypatch.setattr(anchor_mod, "_anchor", fake)
    return calls


def _no_weave(monkeypatch) -> list:
    """No exploration to join and no closing: notes are planted, never woven.
    The weave is still patched so a regression cannot reach a provider."""
    woven: list = []

    async def fake_run(*, perspective_hashes, intent, nexus_hash):
        woven.append(list(perspective_hashes))
        return "{}", []

    monkeypatch.setattr(explore_mod, "run_exploration_detailed", fake_run)
    monkeypatch.setattr(NexusRepository, "find_all", lambda self: [])
    return woven


def _forget_this_process(sid: str) -> None:
    """What a dead worker leaves behind: nothing in RAM. The graph keeps the
    Note; the lease (if any) expires on its own."""
    _DEFERRED_WORK.pop(sid, None)


class TestTheWeaveLeaseIsCompareAndSet:
    """Repository-level: the CAS semantics the Advisor relies on."""

    def test_the_first_owner_holds_and_the_second_is_refused(self):
        case = _case()
        with scope(case.sid):
            repo = CaseRepository()
            assert repo.acquire_weave_lease(owner="a", ttl_s=60) is True
            assert repo.acquire_weave_lease(owner="b", ttl_s=60) is False
            holder = repo.weave_lease_holder()
            assert holder is not None and holder[0] == "a"
            # A non-holder's release is a no-op.
            repo.release_weave_lease(owner="b")
            assert repo.weave_lease_holder()[0] == "a"
            repo.release_weave_lease(owner="a")
            assert repo.weave_lease_holder() is None
            assert repo.acquire_weave_lease(owner="b", ttl_s=60) is True

    def test_an_expired_lease_is_taken_over(self):
        case = _case()
        with scope(case.sid):
            repo = CaseRepository()
            assert repo.acquire_weave_lease(owner="a", ttl_s=0.2) is True
            time.sleep(0.3)
            assert repo.weave_lease_holder() is None, "expired reads as free"
            assert repo.acquire_weave_lease(owner="b", ttl_s=60) is True
            assert repo.acquire_weave_lease(owner="a", ttl_s=60) is False

    def test_renewal_is_the_same_statement(self):
        case = _case()
        with scope(case.sid):
            repo = CaseRepository()
            assert repo.acquire_weave_lease(owner="a", ttl_s=1.0)
            first_until = repo.weave_lease_holder()[1]
            assert repo.acquire_weave_lease(owner="a", ttl_s=60.0)
            assert repo.weave_lease_holder()[1] > first_until

    def test_a_lease_is_per_sid(self):
        one, two = _case(), _case()
        with scope(one.sid):
            assert CaseRepository().acquire_weave_lease(owner="a", ttl_s=60)
        with scope(two.sid):
            assert CaseRepository().acquire_weave_lease(owner="b", ttl_s=60)
            assert CaseRepository().weave_lease_holder()[0] == "b"

    def test_no_scope_no_lease(self):
        with pytest.raises(ValueError):
            CaseRepository().acquire_weave_lease(owner="a", ttl_s=60)


class TestNotesAreDurableOnTheTurn:
    @pytest.mark.asyncio
    async def test_queue_note_commits_the_note_before_it_answers(self):
        case = _case()
        with scope(case.sid):
            advisor = Advisor(build=BuildPolicy.ON_CONSENT)
            reply = await advisor._queue_note("Keep the Berlin office", None, "12 people there")
            assert reply.startswith("Kept.")
            pending = NoteRepository().find_unplanted()
            assert [n.thesis for n in pending] == ["Keep the Berlin office"]
            assert pending[0].context == "12 people there"
            assert pending[0].planted is None
            # A note lives in exactly one place: committed, so NOT in memory.
            assert advisor._notes_awaiting_anchor == []

    @pytest.mark.asyncio
    async def test_the_same_words_kept_twice_are_two_notes(self, monkeypatch):
        """A repeat is a request: `anchor` on identical wording is how an
        alternative tetrad on the same tension is made, so the second keep must
        reach it. (Decision has the same nonce rule for the same reason.)"""
        anchors = _fake_anchor(monkeypatch)
        _no_weave(monkeypatch)
        case = _case()
        with scope(case.sid):
            advisor = Advisor(build=BuildPolicy.ON_CONSENT)
            await advisor._queue_note("Keep the Berlin office", None, "")
            await advisor._queue_note("Keep the Berlin office", None, "")
            assert len(NoteRepository().find_unplanted()) == 2
            advisor._schedule_noted_tensions()
            await advisor.wait_for_deferred_work()
            assert [a["thesis"] for a in anchors] == ["Keep the Berlin office"] * 2
            assert NoteRepository().find_unplanted() == []

    @pytest.mark.asyncio
    async def test_a_fresh_process_plants_what_the_dead_one_kept(self, monkeypatch):
        """The defect: a note queued on worker A, A dies, the person's next
        turn lands on worker B. B has no RAM trace of the note; the graph has
        it; B plants it and stamps it."""
        anchors = _fake_anchor(monkeypatch)
        _no_weave(monkeypatch)
        case = _case()
        with scope(case.sid):
            dying = Advisor(build=BuildPolicy.ON_CONSENT)
            await dying._queue_note("Keep the Berlin office", None, "12 people there")
            (note_hash,) = [n.hash for n in NoteRepository().find_unplanted()]
            _forget_this_process(case.sid)

            resumed = Advisor(build=BuildPolicy.ON_CONSENT)
            assert resumed._notes_awaiting_anchor == [], "nothing in RAM on the new worker"
            resumed._schedule_noted_tensions()
            assert resumed._last_deferral is DeferralOutcome.STARTED
            assert await resumed.wait_for_deferred_work() is True

            assert anchors == [
                {"thesis": "Keep the Berlin office", "antithesis": None, "context": "12 people there"}
            ]
            assert NoteRepository().find_unplanted() == []
            from dialectical_framework.graph.repositories.node_repository import \
                NodeRepository

            note = NodeRepository().find_by_hash(note_hash, node_type=Note)
            assert note is not None and note.planted == "pp0001"

    @pytest.mark.asyncio
    async def test_a_note_another_process_already_planted_is_not_planted_again(
        self, monkeypatch
    ):
        """The graph says it is done (another process got there first): this
        process has nothing in RAM and finds nothing pending. No second anchor,
        no task."""
        anchors = _fake_anchor(monkeypatch)
        _no_weave(monkeypatch)
        case = _case()
        with scope(case.sid):
            advisor = Advisor(build=BuildPolicy.ON_CONSENT)
            await advisor._queue_note("Keep the Berlin office", None, "")
            (note,) = NoteRepository().find_unplanted()
            note.planted = "pp9999"  # the other process's stamp
            note.save()

            advisor._schedule_noted_tensions()
            assert advisor._last_deferral is None, "nothing left to schedule"
            assert advisor._deferred_pathway_task is None
            assert anchors == []

    @pytest.mark.asyncio
    async def test_a_note_whose_commit_failed_is_still_planted_from_memory(
        self, monkeypatch
    ):
        """The pre-durability path survives as the fallback: no Note behind the
        triple means it is planted from the in-memory queue."""
        anchors = _fake_anchor(monkeypatch)
        _no_weave(monkeypatch)
        case = _case()
        with scope(case.sid):
            advisor = Advisor(build=BuildPolicy.ON_CONSENT)
            monkeypatch.setattr(Advisor, "_persist_note", lambda self, t, a, c: None)
            await advisor._queue_note("Keep the Berlin office", None, "")
            assert NoteRepository().find_unplanted() == []
            advisor._schedule_noted_tensions()
            await advisor.wait_for_deferred_work()
            assert [a["thesis"] for a in anchors] == ["Keep the Berlin office"]

    @pytest.mark.asyncio
    async def test_a_note_that_will_not_plant_is_tried_once_per_drain(
        self, monkeypatch
    ):
        """A raised plant keeps the note pending (a transient fault must not
        lose the person's word) but must not spend the round cap on it."""
        attempts: list[str] = []

        async def failing(*, thesis, antithesis, context):
            attempts.append(thesis)
            raise RuntimeError("provider down")

        monkeypatch.setattr(anchor_mod, "_anchor", failing)
        _no_weave(monkeypatch)
        case = _case()
        with scope(case.sid):
            advisor = Advisor(build=BuildPolicy.ON_CONSENT)
            await advisor._queue_note("Keep the Berlin office", None, "")
            advisor._schedule_noted_tensions()
            await advisor.wait_for_deferred_work()
            assert attempts == ["Keep the Berlin office"], (
                f"one attempt per drain, got {len(attempts)}"
            )
            assert len(NoteRepository().find_unplanted()) == 1, "still pending"
            assert CaseRepository().weave_lease_holder() is None

    @pytest.mark.asyncio
    async def test_the_understanding_counts_a_pending_note(self):
        from dialectical_framework.concerns.dialectical_context import \
            DialecticalContext

        case = _case()
        with scope(case.sid):
            advisor = Advisor(build=BuildPolicy.ON_CONSENT)
            await advisor._queue_note("Keep the Berlin office", None, "")
            dump = await DialecticalContext().resolve()
            assert ("kept note(s)" in dump) or ("asked to keep" in dump), dump
            advisor._notes_awaiting_anchor.clear()


class TestATurnWaitsOutAnotherProcess:
    @pytest.mark.asyncio
    async def test_settle_waits_for_a_foreign_lease_to_expire(self, monkeypatch):
        monkeypatch.setattr(advisor_mod, "_WEAVE_LEASE_POLL_S", 0.1)
        case = _case()
        with scope(case.sid):
            CaseRepository().acquire_weave_lease(owner=OTHER_PROCESS, ttl_s=1.0)
            advisor = Advisor(build=BuildPolicy.ON_CONSENT)
            waited = await advisor._settle_deferred_work()
            assert waited >= 0.8, f"did not wait the foreign weave out ({waited:.2f}s)"
            assert CaseRepository().weave_lease_holder() is None

    @pytest.mark.asyncio
    async def test_settle_does_not_wait_on_this_process_own_lease(self):
        case = _case()
        with scope(case.sid):
            CaseRepository().acquire_weave_lease(owner=advisor_mod._WEAVE_OWNER, ttl_s=60)
            advisor = Advisor(build=BuildPolicy.ON_CONSENT)
            waited = await advisor._settle_deferred_work()
            assert waited < 0.5
            CaseRepository().release_weave_lease(owner=advisor_mod._WEAVE_OWNER)

    @pytest.mark.asyncio
    async def test_settle_is_free_when_nobody_holds_the_sid(self):
        case = _case()
        with scope(case.sid):
            advisor = Advisor(build=BuildPolicy.ON_CONSENT)
            assert await advisor._settle_deferred_work() < 0.5

    @pytest.mark.asyncio
    async def test_the_task_stands_down_while_another_process_holds_the_lease(
        self, monkeypatch
    ):
        """Two writers never: the task started here finds the sid leased
        elsewhere, plants nothing, keeps its queue — and the note is planted
        once the lease is free and the next turn re-offers the queue."""
        anchors = _fake_anchor(monkeypatch)
        _no_weave(monkeypatch)
        case = _case()
        with scope(case.sid):
            CaseRepository().acquire_weave_lease(owner=OTHER_PROCESS, ttl_s=60)
            advisor = Advisor(build=BuildPolicy.ON_CONSENT)
            await advisor._queue_note("Keep the Berlin office", None, "")
            advisor._schedule_noted_tensions()
            assert advisor._last_deferral is DeferralOutcome.STARTED
            await advisor.wait_for_deferred_work()

            assert anchors == [], "planted while another process held the sid"
            assert len(NoteRepository().find_unplanted()) == 1, "still queued, in the graph"
            assert CaseRepository().weave_lease_holder()[0] == OTHER_PROCESS, (
                "a task that never held the lease must not release it"
            )

            # The other process finishes; this process's next turn re-offers.
            CaseRepository().release_weave_lease(owner=OTHER_PROCESS)
            advisor._last_deferral = None
            advisor._schedule_noted_tensions()
            await advisor.wait_for_deferred_work()
            assert [a["thesis"] for a in anchors] == ["Keep the Berlin office"]
            assert NoteRepository().find_unplanted() == []

    @pytest.mark.asyncio
    async def test_the_task_holds_the_lease_while_it_runs_and_releases_after(
        self, monkeypatch
    ):
        block = asyncio.Event()
        _fake_anchor(monkeypatch, block=block)
        _no_weave(monkeypatch)
        case = _case()
        with scope(case.sid):
            advisor = Advisor(build=BuildPolicy.ON_CONSENT)
            await advisor._queue_note("Keep the Berlin office", None, "")
            advisor._schedule_noted_tensions()
            await asyncio.sleep(0.05)  # let the task take the lease and block
            holder = CaseRepository().weave_lease_holder()
            assert holder is not None and holder[0] == advisor_mod._WEAVE_OWNER
            block.set()
            await advisor.wait_for_deferred_work()
            assert CaseRepository().weave_lease_holder() is None

    @pytest.mark.asyncio
    async def test_a_decision_left_waiting_is_re_offered_by_the_next_turn(
        self, monkeypatch
    ):
        """A closing whose task stood down (lease elsewhere) is grounded by a
        later turn that neither closes nor notes — the queue is not forgotten
        until the next closing."""
        _no_weave(monkeypatch)
        grounded: list = []
        monkeypatch.setattr(
            Advisor, "_ground_recorded_decision", lambda self, h, p: grounded.append(h)
        )
        monkeypatch.setattr(Advisor, "_anchor_when_empty", _false)
        case = _case()
        with scope(case.sid):
            CaseRepository().acquire_weave_lease(owner=OTHER_PROCESS, ttl_s=60)
            advisor = Advisor(build=BuildPolicy.ON_CONSENT)
            advisor._schedule_pathway_construction("dec00001")
            await advisor.wait_for_deferred_work()
            assert grounded == []
            assert advisor._decisions_awaiting_pathway == ["dec00001"]

            CaseRepository().release_weave_lease(owner=OTHER_PROCESS)
            advisor._last_deferral = None
            advisor._schedule_noted_tensions()  # a plain turn: no note, no closing
            assert advisor._last_deferral is DeferralOutcome.STARTED
            await advisor.wait_for_deferred_work()
            assert grounded == ["dec00001"]


async def _false(self, pending) -> bool:
    return False


class TestDrainingAWholeProcess:
    @pytest.mark.asyncio
    async def test_drain_deferred_work_covers_every_sid(self, monkeypatch):
        block = asyncio.Event()
        _fake_anchor(monkeypatch, block=block)
        _no_weave(monkeypatch)
        one, two = _case(), _case()
        for case in (one, two):
            with scope(case.sid):
                advisor = Advisor(build=BuildPolicy.ON_CONSENT)
                await advisor._queue_note("Keep the Berlin office", None, "")
                advisor._schedule_noted_tensions()
        await asyncio.sleep(0.05)
        assert deferred_work_in_flight(one.sid) and deferred_work_in_flight(two.sid)

        # Bounded: returns False with the work still running, cancels nothing.
        assert await drain_deferred_work(timeout=0.2) is False
        assert deferred_work_in_flight(one.sid)

        block.set()
        assert await drain_deferred_work() is True
        assert not deferred_work_in_flight(one.sid)
        assert not deferred_work_in_flight(two.sid)
        for case in (one, two):
            with scope(case.sid):
                assert NoteRepository().find_unplanted() == []

    @pytest.mark.asyncio
    async def test_drain_with_nothing_in_flight_is_true(self):
        assert await drain_deferred_work() is True
        assert deferred_work_in_flight("nobody") is False
