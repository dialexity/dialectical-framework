"""The seven tools that had instrumentation inside and no scope above it.

WHY THIS FILE EXISTS
====================
`report_progress` is a deliberate no-op when no scope is installed — that is what
lets it sit on a hot path — so a tool that never calls `progress_scope` is SILENT no
matter how thoroughly the code beneath it reports. `analyze` was the expensive
lesson: one `with` lit up 31 already-written calls across six modules
(`tests/test_analyze_progress.py`). These seven are the rest of that set, and every
one of them was reachable directly by a model:

    find_polarities    -> stage `opposition`
    surface_theses     -> stage `extraction`
    expand_polarities  -> stage `expansion`
    anchor_theses      -> stage `anchor`
    introduce_polarity -> stage `anchor`
    digest_input       -> stage `ingest`
    add_input          -> stage `ingest`

**Nothing about this defect looks wrong at either end**, which is why the assertions
are behavioural. Every reporting site was already correct. Every unit test on those
sites already passed. The tools returned the right answers. The only observable was a
person sitting through the whole wait with nothing on screen — and no assertion about
a scope OBJECT can see it, because on the broken path the object is never created.

WHAT EACH TEST PINS, AND WHY IT IS THE LOAD-BEARING ONE
=======================================================
For every tool: a label published DEEP under the tool reaches the bus. Deleting the
`with` leaves the tool working, the sub-tests green and this assertion failing, which
is the only signal the defect ever gave.

For `expand_polarities` that assertion carries a second guarantee: all of its work
runs inside an `asyncio.gather` the TOOL creates, and a task created before the scope
is installed captured a copy of the context and can never see it. So a `with` placed
one line lower there would publish a tidy `final` over total silence.

Two stage names are REUSED — `anchor` by two skills and the Advisor's own `anchor`
tool, `ingest` by two tools and the Advisor's `ingest`. That is safe because a nested
`progress_scope` defers rather than installing, and it is pinned here against the REAL
skills rather than stubs (`test_progress.py`'s deferral class uses stubs). What that
catches is an inner scope that INSTALLS; an inner scope DELETED leaves it green just as
the stubbed version would, since the events land in the outer stream either way — see
that test's own docstring.

Mock brain throughout: this is about the accounting, not the reasoning.

Run: poetry run pytest tests/test_tool_progress_scopes.py
"""

from __future__ import annotations

import asyncio

import pytest

from dialectical_framework.events.graph_event_bus import GraphEventBus
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.polarity import Polarity
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.scope_context import scope
from dialectical_framework.utils import progress as progress_module
from dialectical_framework.utils.progress import (progress_hash_key,
                                                  progress_key,
                                                  progress_scope)

#: Terms a host may not render to a person. Kept in step with the copies in
#: `test_ingest_progress.py` / `test_analyze_progress.py` / `test_edit_progress.py`
#: — the same contract, different entry points. Stage names are checked against this
#: too, which is why none of these tools reuses its own name as its stage.
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
)

_T_MEANING = "dx://taxonomy/System(General.v1)/Viability/Integrity/Coherence"
_A_MEANING = "dx://taxonomy/System(General.v1)/Viability/Integrity/Separation"

#: Long enough that any run of it inside a label or a key is a leak, not a
#: coincidence of ordinary English.
SOURCE = (
    "Ravensbourne kept promising delivery dates it could not hold, and the people "
    "who noticed first were the ones with the least standing to say so."
)
_LEAK_RUN = 40


@pytest.fixture
async def bus():
    """Subscribe-able bus for one run, wired into the progress seam."""
    b = GraphEventBus()
    await b.connect()
    # RESTORE, never clear: the module-level bus is wired once by the session-scoped
    # `di_container` fixture, so `None` here would silently disable progress for
    # every test that ran afterwards.
    previous = progress_module._event_bus
    progress_module.set_event_bus(b)
    try:
        yield b
    finally:
        progress_module.set_event_bus(previous)
        await b.disconnect()


async def _drain(received: list, *, timeout: float = 5.0) -> None:
    """Wait until `received` stops growing.

    Not a fixed sleep: publishes are fire-and-forget `create_task`s, so a fixed
    interval passes on an idle machine and drops the closing event under load —
    which reads as a missing `final` rather than as flake.
    """
    previous = -1
    waited = 0.0
    while previous != len(received) and waited < timeout:
        previous = len(received)
        await asyncio.sleep(0.05)
        waited += 0.05


async def _collect(bus, sid: str, run, *, expect_raise=None) -> list:
    """Run `run()` under `sid` while draining that sid's progress channel.

    The `scope` is entered around the AWAIT, not around building the coroutine:
    `_publish` drops every event when no sid is in scope, so a factory that left the
    `with` before anything ran would report "the person saw silence" about the
    harness rather than about the tool.
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
            if expect_raise is not None:
                with pytest.raises(expect_raise):
                    await run()
            else:
                await run()
        await _drain(received)
    finally:
        listener.cancel()
    return received


def _assert_stream_is_sane(events: list, *, stage: str, key: str) -> list:
    """Everything true of EVERY stream on this channel, whichever tool opened it.

    Returns the step details, so each test can then assert on the one label that
    proves the scope is in the right place.
    """
    assert events, "not one progress event — the person saw silence"

    finals = [e for e in events if e.final]
    # Notes are not steps and must be excluded from every count: that is the whole
    # reason `ProgressEvent.note` exists rather than completions riding on
    # `report_progress`, which would push `done` past `total`.
    notes = [e for e in events if e.note and not e.final]
    steps = [e for e in events if not e.final and not e.note]

    assert len(finals) == 1, (
        f"expected exactly one closing event, got {len(finals)} — a host clears its"
        f" indicator on `final`, so two means it cleared mid-run"
    )
    final = finals[0]
    assert final.done == final.total, (
        f"closed at {final.done}/{final.total} — every step on these paths is"
        f" declared at its own site, so a shortfall means work was declared for a"
        f" branch that never ran: a phantom step, a bar that cannot fill"
    )
    for i, event in enumerate(steps):
        assert event.done == i, (
            f"step {i} published done={event.done} — counters are snapshotted at"
            f" publish time precisely so gathered events do not all carry the same"
            f" number"
        )
    for note in notes:
        assert note.done <= note.total, (
            "a note moved the counters past the denominator, which is the one thing"
            " `note=True` is supposed to make impossible"
        )

    assert {e.stage for e in events} == {stage}, (
        f"more than one stage on this channel:"
        f" {sorted({e.stage for e in events})} — an inner stage name appearing here"
        f" means a nested scope installed instead of deferring"
    )
    assert {e.key for e in events} == {key}, (
        f"the stream is not keyed the way the tool documents:"
        f" {sorted({e.key for e in events})} != {key!r}. Two calls of one tool can be"
        f" in flight in one round, and without a stable key their counts interleave"
        f" into a single nonsensical bar"
    )

    for term in BANNED:
        # `stage` is as visible as `detail`: a host has to write its own label from
        # it. This is why none of these tools reuses its own name as its stage.
        assert term not in stage.lower(), f"stage {stage!r} names the machinery"

    for event in events:
        lowered = event.detail.lower()
        for term in BANNED:
            assert term not in lowered, (
                f"label {event.detail!r} names the machinery ({term!r}) — the silent"
                f" Advisor's contract is that a host may render these verbatim"
            )
        assert len(event.detail) < 200, (
            f"label is {len(event.detail)} chars: too long to be a label and long"
            f" enough to be carrying content"
        )
        if event.final:
            assert event.detail == "", (
                f"the closing event labelled itself {event.detail!r}; the label beside"
                f" a host's spinner is the host's to write, from `stage`, `key`,"
                f" `done` and `total`"
            )

    return [e.detail for e in steps]


def _assert_no_leak(events: list, text: str) -> None:
    """No run of the person's own words in a label OR in the key.

    The key needs this as much as the labels do: on four of these tools it is derived
    FROM the person's text, and an edit that passed the text through instead of
    hashing it would still be "keyed", still stable, still unique — and would put
    their own sentence next to a host's spinner.
    """
    for event in events:
        for start in range(0, max(1, len(text) - _LEAK_RUN)):
            run = text[start : start + _LEAK_RUN]
            assert run not in event.detail, f"text leaked into {event.detail!r}"
            assert run not in (event.key or ""), "text leaked into the key"


def _two_theses(sid: str) -> list[str]:
    with scope(sid):
        t1 = Statement(text="Hire fast to meet demand", meaning=_T_MEANING)
        t1.commit()
        t2 = Statement(text="Hire slowly to keep oversight", meaning=_A_MEANING)
        t2.commit()
        return [t1.hash, t2.hash]


def _one_polarity(sid: str) -> str:
    with scope(sid):
        t = Statement(text="Speed", meaning=_T_MEANING)
        t.commit()
        a = Statement(text="Care", meaning=_A_MEANING)
        a.commit()
        pol = Polarity()
        pol.set_t(t, heuristic_similarity=1.0)
        pol.set_a(a, heuristic_similarity=0.8)
        pol.commit()
        return pol.hash


@pytest.mark.llm
@pytest.mark.asyncio
async def test_find_polarities_speaks_from_two_depths(bus):
    """The longest silence on the Analyst's path, and it needed no new sites.

    Two labels are asserted, from two depths, and the pairing is what distinguishes
    "a scope exists" from "the scope is in the right place": the consolidation label
    comes from `FindPolarities.resolve()`, which the tool awaits directly, while the
    antithesis label comes from inside a `gather` that `resolve` creates.
    """
    from dialectical_framework.agents.analyst.skills.find_polarities import \
        find_polarities

    case = Case()
    case.commit()
    hashes = _two_theses(case.sid)

    events = await _collect(
        bus,
        case.sid,
        lambda: find_polarities.fn(thesis_hashes=hashes, count=2),
    )
    key = progress_key(sorted({progress_hash_key(h) for h in hashes}))
    details = _assert_stream_is_sane(events, stage="opposition", key=key)

    assert any("already oppose each other" in d for d in details), (
        f"the consolidation phase never spoke: {details}"
    )
    assert any("Weighing what could stand against this" in d for d in details), (
        f"nothing inside the antithesis fan-out reported — this is what a scope"
        f" installed too late breaks while still closing tidily: {details}"
    )
    assert any(e.note for e in events), (
        "no returning angle was noted; `AntithesisExtraction`'s gather is one of"
        " only two `note_progress` sites in the tree and this tool reaches it"
    )


@pytest.mark.llm
@pytest.mark.asyncio
async def test_expand_polarities_installs_above_its_own_gather(bus):
    """Every step here is inside a `gather` the TOOL builds, which is the whole test.

    A task created before the scope is installed holds a context copy that does not
    point at it, so a `with` opened one line lower — after `unique_hashes` was mapped
    into coroutines — would leave all of this mute and still publish a tidy `final`.
    Nothing else in this file can catch that.
    """
    from dialectical_framework.agents.analyst.skills.expand_polarities import \
        expand_polarities

    case = Case()
    case.commit()
    polarity_hash = _one_polarity(case.sid)

    events = await _collect(
        bus,
        case.sid,
        lambda: expand_polarities.fn(polarity_hashes=[polarity_hash]),
    )
    key = progress_key([progress_hash_key(polarity_hash)])
    details = _assert_stream_is_sane(events, stage="expansion", key=key)

    assert any("overreaches" in d for d in details), (
        f"the aspect-generation step never announced itself: {details}"
    )


@pytest.mark.llm
@pytest.mark.asyncio
async def test_expand_polarities_keys_on_the_work_it_actually_does(bus):
    """Duplicates are dropped BEFORE the key is built, like `audit_feasibility`'s.

    The key comes from `unique_hashes`, not from the argument, so the key and the
    denominator describe the same work — a model naming one Polarity twice must not
    key a different stream from one naming it once.
    """
    from dialectical_framework.agents.analyst.skills.expand_polarities import \
        expand_polarities

    case = Case()
    case.commit()
    polarity_hash = _one_polarity(case.sid)

    events = await _collect(
        bus,
        case.sid,
        lambda: expand_polarities.fn(
            polarity_hashes=[polarity_hash, f"[[{polarity_hash}]]", polarity_hash]
        ),
    )
    assert events
    # Three arguments, two spellings, ONE Polarity — and one stream, identical to the
    # key the plain single-hash call above produces. `dict.fromkeys` cannot get this
    # on its own: it dedups the RAW strings, so the bracketed spelling survives it and
    # sanitising then collapses the two, which is why the key is built from a set.
    assert {e.key for e in events} == {
        progress_key([progress_hash_key(polarity_hash)])
    }
    for event in events:
        assert "[" not in (event.key or ""), (
            f"the key kept the model's brackets: {event.key!r} — the framework"
            f" renders hashes as `[[abc1234]]`, so an echoing model would put prompt"
            f" punctuation beside a host's spinner"
        )


@pytest.mark.llm
@pytest.mark.asyncio
async def test_surface_theses_speaks_and_hides_the_persons_wording(bus):
    """The one site in the tree whose denominator is known in advance.

    `intent` is the person's own extraction wording, so the key is a digest of it —
    checked here rather than only in a key test, because a key that merely "exists"
    can still be the sentence itself.
    """
    from dialectical_framework.agents.analyst.skills.surface_theses import \
        surface_theses
    from dialectical_framework.concerns.add_input import AddInput

    case = Case()
    case.commit()
    with scope(case.sid):
        await AddInput().resolve(content=SOURCE)

    intent = f"find the tension behind this: {SOURCE}"
    events = await _collect(
        bus,
        case.sid,
        lambda: surface_theses.fn(intent=intent),
    )
    key = progress_key(intent, None)
    details = _assert_stream_is_sane(events, stage="extraction", key=key)
    _assert_no_leak(events, SOURCE)

    assert any("Reading the material for tensions" in d for d in details), (
        f"extraction never announced itself: {details}"
    )


@pytest.mark.llm
@pytest.mark.asyncio
async def test_anchor_theses_publishes_under_the_anchor_stage(bus):
    """A person's named concepts, and the same stage the Advisor's `anchor` uses."""
    from dialectical_framework.agents.analyst.skills.anchor_theses import \
        anchor_theses

    case = Case()
    case.commit()
    statements = ["Trust", "Oversight"]

    events = await _collect(
        bus,
        case.sid,
        lambda: anchor_theses.fn(statements=statements),
    )
    key = progress_key(statements, None)
    details = _assert_stream_is_sane(events, stage="anchor", key=key)

    assert any("Taking in the position you named" in d for d in details), (
        f"the classification step never announced itself: {details}"
    )


@pytest.mark.llm
@pytest.mark.asyncio
async def test_introduce_polarity_keys_exactly_as_the_advisor_anchor_does(bus):
    """Same arguments, same digest — one wording is one stream, whichever door.

    Asserted against `advisor.tools.anchor._progress_key` itself rather than against
    a recomputation, because the point is the two entry points AGREEING: a model that
    plants the same tension through either tool must not open two bars.
    """
    from dialectical_framework.agents.advisor.tools.anchor import \
        _progress_key as anchor_tool_key
    from dialectical_framework.agents.analyst.skills.introduce_polarity import \
        introduce_polarity

    case = Case()
    case.commit()
    thesis, antithesis = "Move fast on the Ravensbourne offer", "Wait for the audit"

    events = await _collect(
        bus,
        case.sid,
        lambda: introduce_polarity.fn(thesis=thesis, antithesis=antithesis),
    )
    details = _assert_stream_is_sane(
        events, stage="anchor", key=anchor_tool_key(thesis, antithesis)
    )
    _assert_no_leak(events, thesis + " " + antithesis)

    assert any("Taking in both sides of what you described" in d for d in details), (
        f"the two-pole classification step never announced itself: {details}"
    )


@pytest.mark.llm
@pytest.mark.asyncio
async def test_digest_input_keys_by_the_node_and_says_it_is_reading(bus):
    """Keyed RAW, unlike the four text-keyed tools, and that is the deliberate half.

    The argument is already an opaque hash, so digesting it would hide nothing and
    cost a host the one thing a key is good for — lining its bar up with the source
    the person just named.
    """
    from dialectical_framework.agents.orchestrator.tools.digest_input import \
        digest_input
    from dialectical_framework.concerns.add_input import AddInput

    case = Case()
    case.commit()
    with scope(case.sid):
        # Over `DIGEST_THRESHOLD`, so a provider call actually happens; under
        # `CHUNK_SIZE`, so it is the single-pass branch and not the parts fan-out.
        node = await AddInput().resolve(content=SOURCE * 40)
        input_hash = node.hash

    events = await _collect(
        bus, case.sid, lambda: digest_input.fn(input_hash=input_hash)
    )
    details = _assert_stream_is_sane(
        events, stage="ingest", key=progress_hash_key(input_hash)
    )
    _assert_no_leak(events, SOURCE)

    assert details == ["Building a working understanding of it"], (
        f"the single-pass reading is what this whole stream is: {details}. It is"
        f" declared inside `SourceDigest._generate_digest` rather than at a caller,"
        f" because `resolve` returns without a call at all on compact content"
    )


@pytest.mark.llm
@pytest.mark.asyncio
async def test_digest_input_sanitises_a_bracketed_hash_before_keying(bus):
    """The scope opens ABOVE any attempt to resolve the hash, so the key is raw output.

    The framework renders hashes into prompts as `[[abc1234]]` and an echoing model is
    the most common malformed-hash shape in this tree. The stream must still be keyed
    on the node — two spellings of ONE source getting two keys is the single thing a
    key exists to prevent — while the ARGUMENT is passed on untouched, so resolution
    fails exactly as it did before. Only the key is sanitised.
    """
    from dialectical_framework.agents.orchestrator.tools.digest_input import \
        digest_input

    case = Case()
    case.commit()
    bogus = "0123456789abcdef"

    events = await _collect(
        bus,
        case.sid,
        lambda: digest_input.fn(input_hash=f"  [[{bogus}]]  "),
        expect_raise=ValueError,
    )
    assert events, "a tool that raises must still close its stream"
    assert {e.key for e in events} == {bogus[:7]}, (
        f"key is {sorted({e.key for e in events})} — brackets and whitespace from a"
        f" prompt template reached a host-rendered surface"
    )
    finals = [e for e in events if e.final]
    assert len(finals) == 1 and finals[0].done == finals[0].total == 0, (
        f"expected one close at 0/0 on the unresolvable branch, got"
        f" {[(e.done, e.total) for e in finals]}: a step declared above the lookup"
        f" would be announced and never reported"
    )


@pytest.mark.llm
@pytest.mark.asyncio
async def test_add_input_covers_capture_and_reading_as_one_stream(bus):
    """One action to the person, so one stream — and the key digests their material.

    `content` is whole pasted documents on this path, which is the central case for
    hashing a key rather than keeping it readable.
    """
    from dialectical_framework.agents.orchestrator.tools.add_input import \
        add_input

    case = Case()
    case.commit()
    content = SOURCE * 40

    events = await _collect(bus, case.sid, lambda: add_input.fn(content=content))
    details = _assert_stream_is_sane(
        events, stage="ingest", key=progress_key(content)
    )
    _assert_no_leak(events, SOURCE)

    assert any("Building a working understanding of it" in d for d in details), (
        f"the reading behind the capture never announced itself: {details}"
    )


@pytest.mark.llm
@pytest.mark.asyncio
async def test_the_reused_stage_names_are_safe_because_nesting_defers(bus):
    """Two skills claim `anchor` and two tools claim `ingest`. This is why that holds.

    `test_progress.py::TestNestingDefersToTheInstalledScope` pins the seam using
    STUBS, so a skill that quietly dropped its own `progress_scope` would leave it
    green. This drives the real tools under an outer scope: whatever they declare must
    fold into the outer stream, and the outer `final` must be the only one.

    **Which is about the SEAM, not about the skill's scope existing.** Delete
    `introduce_polarity`'s own `progress_scope` and its `report_progress` calls publish
    into the outer stream instead — one stage, one key, one `final`, still green. What
    fails here is the reverse: an inner scope that INSTALLS puts its own stage name on
    the channel. Pinning that a skill installs a scope at all needs it run with nothing
    outer (`test_explore_progress_scope.py::TestTheTwoSkillsInstallTheirOwnScopes`).
    """
    from dialectical_framework.agents.analyst.skills.introduce_polarity import \
        introduce_polarity

    case = Case()
    case.commit()

    async def _under_an_outer_scope() -> None:
        with progress_scope("outer-owner", key="owner-key"):
            await introduce_polarity.fn(thesis="Speed", antithesis="Care")

    events = await _collect(bus, case.sid, _under_an_outer_scope)
    assert events

    assert {e.stage for e in events} == {"outer-owner"}, (
        f"stages seen: {sorted({e.stage for e in events})} — the skill installed its"
        f" own scope instead of deferring, so the tool that composes it would publish"
        f" two streams for one action"
    )
    assert {e.key for e in events} == {"owner-key"}
    finals = [e for e in events if e.final]
    assert len(finals) == 1, (
        f"{len(finals)} closing events for one action — this is exactly the `deepen`"
        f" defect, where a host cleared its indicator halfway through"
    )
    steps = [e for e in events if not e.final and not e.note]
    assert steps, "the skill's steps were dropped rather than folded into the outer"
    assert finals[0].total == len(steps), (
        f"the inner declarations did not reach the outer denominator:"
        f" {finals[0].done}/{finals[0].total} against {len(steps)} steps"
    )
