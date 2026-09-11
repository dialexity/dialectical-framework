"""What the ARCHIVE records when a turn does not finish, and what readers do with it.

`tests/test_turn_timing.py` pins the agent side: that a turn assembles an honest
`TurnTiming`. This file pins the hop after it — driver to `TurnRecord` to the two
readers — and it exists because that hop had a default that lied.

Five of `TurnRecord`'s timing fields defaulted to zero — `reply_path_s`,
`off_path_s`, `context_render_s`, `retry_seconds` at `0.0` and `retry_count` at
`0`; `first_delta_s` is newer than the defect and was born `None` — and the driver
wrote those defaults whenever `arm.last_turn_timing` was None. None is exactly what
an arm publishes when its turn RAISED, because timing is assembled after the reply.
So a failed turn would have been archived as a turn that took no time — the case is
MECHANICAL, not observed: all 62 error turns in the archive predate these fields,
so nothing was ever actually recorded that way. What it would have cost is
specific, which is why the fix is worth its tests. A crashed turn would have
entered every split column as instant; `retry_count=0` would have claimed a clean
turn for one that died mid-ladder; and because `duration_s` is real and often large
on those records, the `duration_s ≈ reply_path_s + off_path_s` check would have
reported the entire turn as harness overhead. Same shape as the
`last_submit_seconds` defect one layer down (see `ConversationFacilitator`): a zero
is not a gap, it is a claim.

Resist one tempting sharpening of that argument, which stood here for a day: "and
a crash lands in the tool-heavy turns, so the turns most able to move a median
would have entered it as instant". The archive cannot be asked — `driver.py`'s
`except` branch sets `tool_calls = []`, so every one of the 62 error turns records
zero tool calls by construction. The fix needs no such premise: a wrong split is
wrong on an ordinary turn too.

Two halves, and both are needed — fixing either alone leaves the number wrong:

1. The record must say `None`. Tested against the driver's real turn loop rather
   than by constructing `TurnRecord` directly, since the defect lived in the
   driver's `if timing else 0.0`, not in the model.
2. The readers must SKIP the `None`s and SAY how many they skipped. A reader that
   coerces with `or 0.0` reinstates the whole bug while the archive stays honest,
   which is strictly harder to notice than the original.

`duration_s` is deliberately still non-Optional and still written on a crash: the
driver measures it outside the try, so it is the one figure a failed turn can
report, and the one column on which arms with different timing habits stay
comparable (see `PromptArm.last_turn_timing`).
"""

from __future__ import annotations

import json
import time
from typing import Optional

import pytest

from dialectical_framework.agents.turn_timing import ToolRound, TurnTiming
from e2e.driver import E2EDriver
from e2e.models import Beat, RunRecord, SessionRecord, TurnRecord
from e2e.probe_reply_path_latency import _is_measured, _report_measured
from e2e.read_turn_timing import _arms, _stats, _with_arm


class _FakeSettings:
    """Enough of `Settings` for `using_model`'s copy-and-restore dance."""

    ai_model = "stub"

    def model_copy(self, update: dict) -> "_FakeSettings":
        return self


class _FakeProvider:
    def __call__(self) -> _FakeSettings:
        return _FakeSettings()

    def override(self, _value) -> None:
        pass

    def reset_override(self) -> None:
        pass


class _FakeContainer:
    """The driver touches the container only through `using_model`.

    A fake rather than the `di_container` fixture on purpose: this test is about
    arithmetic on the way to a JSON record, and pulling in real settings would
    make a graph-backed fixture a prerequisite for asserting that a float is
    None.
    """

    def __init__(self) -> None:
        self.settings = _FakeProvider()


class _Simulator:
    """Literal beats only, so `next_turn` is never reached."""

    def observe(self, _role: str, _text: str) -> None:
        pass

    async def next_turn(self, _instruction: str) -> str:  # pragma: no cover
        raise AssertionError("literal beats must not consult the simulator")


class _Arm:
    """Replies as told, and publishes the timing an arm of its kind would.

    `raises` models the case the archive got wrong: the turn spends real seconds
    and then dies, so `last_turn_timing` is never assigned and stays None.
    """

    def __init__(
        self,
        *,
        timing: Optional[TurnTiming] = None,
        raises: bool = False,
        spend_s: float = 0.0,
    ) -> None:
        self._timing = timing
        self._raises = raises
        self._spend_s = spend_s
        self.last_tool_calls: list[str] = []
        self.last_tool_outcomes: list[str] = []
        self.last_grounding_args: list[str] = []
        self.last_turn_timing: Optional[TurnTiming] = None

    async def reply(self, _text: str) -> str:
        if self._spend_s:
            time.sleep(self._spend_s)
        if self._raises:
            # Before any assignment below, which is the whole point: a turn that
            # raises has published nothing.
            raise RuntimeError("tool round died")
        self.last_turn_timing = self._timing
        return "reply"


async def _run_one(arm) -> TurnRecord:
    driver = E2EDriver(_FakeContainer(), simulator_model="stub")
    turns = await driver._run_beats(
        arm,
        _Simulator(),
        [Beat(text="hello", tag="opener")],
        tier_model="stub",
    )
    assert len(turns) == 1
    return turns[0]


#: Long enough to survive rounding to one decimal, since the point of the
#: assertion it serves is that the recorded figure is not zero.
_SIMULATOR_SPEND_S = 0.15


def _turn(**fields) -> TurnRecord:
    return TurnRecord(index=0, user="u", assistant="a", **fields)


def _run(
    turns: list[TurnRecord], *, tier: str = "weak", arm: str = "A2"
) -> RunRecord:
    return RunRecord(
        arm=arm,
        tier=tier,
        model="stub",
        scenario_key="k",
        replicate=1,
        duration_s=sum(t.duration_s for t in turns),
        sessions=[SessionRecord(label="s", turns=turns)],
    )


class TestTheDriverArchivesAGapAsAGap:
    @pytest.mark.asyncio
    async def test_a_crashed_turn_records_no_split_at_all(self):
        """The defect this file exists for, at the site it lived.

        `_SPEND_S` is small but non-zero so `duration_s` has something to be
        real ABOUT: the assertion that matters is not merely "the splits are
        None", it is that the record simultaneously says the turn cost seconds
        and says it cannot account for them. A record with `duration_s` 0.0
        would satisfy the None checks while proving nothing.
        """
        _SPEND_S = 0.05
        record = await _run_one(_Arm(raises=True, spend_s=_SPEND_S))

        assert record.error is not None and "RuntimeError" in record.error
        assert record.duration_s >= _SPEND_S

        assert record.reply_path_s is None
        assert record.off_path_s is None
        assert record.context_render_s is None
        assert record.retry_seconds is None
        assert record.retry_count is None
        assert record.first_delta_s is None
        # Lists, not None, and the model says why: an empty list already reads
        # as "nothing recorded" and every consumer iterates them.
        assert record.tool_seconds == []
        assert record.tool_retry_seconds == []

    @pytest.mark.asyncio
    async def test_a_healthy_turn_carries_every_split_through(self):
        """Plumbing, and the precisions are part of it.

        `context_render_s` is recorded to THREE decimals where its neighbours
        get one, because the field's whole purpose is being small against them:
        at 0.1s a 40ms refresh records as a literal 0.0, which is
        indistinguishable from a refresh that never fired. The value here is
        chosen so a one-decimal rounding would destroy it.
        """
        timing = TurnTiming(
            reply_path_s=12.34,
            # 1.26, not 1.25: a value exactly on the boundary rounds by Python's
            # banker's rule, so the assertion below would encode the rounding
            # MODE rather than the plumbing, and read like a typo.
            off_path_s=1.26,
            context_render_s=0.0416,
            tool_rounds=[ToolRound(names=("anchor",), seconds=8.5)],
            retry_seconds=2.5,
            retry_count=3,
            first_delta_s=4.44,
        )
        record = await _run_one(_Arm(timing=timing))

        assert record.error is None
        assert record.reply_path_s == 12.3
        assert record.off_path_s == 1.3
        assert record.context_render_s == 0.042
        assert record.retry_seconds == 2.5
        assert record.retry_count == 3
        assert record.first_delta_s == 4.4
        assert record.tool_seconds == ["anchor:8.5s"]

    @pytest.mark.asyncio
    async def test_an_awaited_turns_first_delta_stays_absent(self):
        """`None`, never 0.0 — and this is today's ordinary case, not an edge.

        Every arm in the bench awaits `chat()`, so nothing populates a first
        delta yet. Recording 0.0 for them would put "the reply appeared
        instantly" into the archive for the arms whose whole problem is how long
        the screen stays blank, and the median would then be a median of a
        fiction. The rest of the split is present, which is what makes the
        absence readable as "not measured" rather than "turn failed".
        """
        record = await _run_one(
            _Arm(timing=TurnTiming(reply_path_s=9.0, off_path_s=0.0))
        )

        assert record.first_delta_s is None
        assert record.reply_path_s == 9.0

    @pytest.mark.asyncio
    async def test_a_simulator_failure_records_no_split_either(self):
        """The other way to get a turn with no timing, and it must agree.

        The simulator branch builds its `TurnRecord` from a different place in
        the driver, so nothing but a test keeps the two paths from disagreeing
        about what an unmeasured turn looks like.
        """

        class _DeadSimulator(_Simulator):
            async def next_turn(self, _instruction: str) -> str:
                time.sleep(_SIMULATOR_SPEND_S)
                raise RuntimeError("simulator died")

        driver = E2EDriver(_FakeContainer(), simulator_model="stub")
        turns = await driver._run_beats(
            _Arm(),
            _DeadSimulator(),
            [Beat(kind="directed", text="push back", tag="pushback_1")],
            tier_model="stub",
        )

        assert len(turns) == 1
        assert turns[0].error is not None and "simulator" in turns[0].error
        assert turns[0].reply_path_s is None
        assert turns[0].retry_count is None
        # And `duration_s` is TIMED here, not the 0.0 default: this branch builds
        # its record inside its own `except`, so the field exempted from the
        # Optional treatment was the one place still able to write a zero-second
        # claim. Mechanical, like the rest of this file: the archive holds 18
        # simulator-failure records and NONE of them carries a `duration_s` key at
        # all, so no zero was ever actually published. The seconds are the
        # simulator's, which the `simulator:` prefix above is what declares.
        assert turns[0].duration_s >= _SIMULATOR_SPEND_S


class TestReadersDropUnmeasuredTurnsAndSaySo:
    #: One healthy turn and one crash. Deliberately two, not more: with a single
    #: healthy turn the median IS that turn, so any reader that failed to drop
    #: the crash would move the figure — the smallest sample that can fail.
    def _mixed(self) -> list[TurnRecord]:
        return [
            _turn(
                duration_s=20.0,
                reply_path_s=18.0,
                off_path_s=2.0,
                context_render_s=0.1,
                retry_seconds=0.0,
                retry_count=0,
            ),
            _turn(duration_s=240.0),  # crashed: no split published
        ]

    def test_the_timing_reader_reports_the_median_of_what_it_measured(self):
        stats = _stats([_run(self._mixed()).model_dump()])

        assert stats["turns"] == 2
        assert stats["untimed turns (dropped)"] == 1
        # 18.0, not 9.0 — the average of a real turn and a fiction.
        assert stats["median reply path"] == 18.0
        assert stats["worst reply path"] == 18.0
        # `duration_s` keeps BOTH turns: it is real on a crash, and the crash is
        # the turn a latency reader most needs to see.
        assert stats["median turn"] == 130.0
        assert stats["worst turn"] == 240.0
        # Over the timed turns only. Counting the crash as a failure to close
        # would report a broken invariant where there is a missing measurement.
        assert stats["arithmetic closes"] == "1/1"

    def test_the_timing_reader_does_not_coerce_a_missing_split_to_zero(self):
        """The `or 0.0` trap, pinned directly.

        `col()` read `float(t.get(key, 0.0) or 0.0)`, which turns None into a
        zero-second turn — and would also flatten a genuine 0.0. Both live here:
        the tool-free median must see the real 0.0 off-path turn and not the
        crash.
        """
        stats = _stats([_run(self._mixed()).model_dump()])

        assert stats["median off path"] == 2.0
        # The healthy turn has no tool_seconds, so it IS the tool-free sample.
        assert stats["median reply path, tool-free"] == 18.0
        # Neither turn streamed, so the count is 0 — not 2 with a median of 0.0,
        # which is what a coercing reader prints and what would read as "both
        # turns replied instantly".
        assert stats["turns with a first delta"] == 0
        assert stats["median first delta"] == "not recorded"

    def test_the_timing_reader_counts_first_deltas_separately(self):
        """Sparser than its neighbours: a timed turn need not have streamed.

        So the count is its own row rather than borrowed from the timed-turn
        count — otherwise a stem where one arm streams and another awaits
        reports a median over a denominator that never applied to it.
        """
        turns = self._mixed()
        turns.append(
            _turn(duration_s=10.0, reply_path_s=9.0, off_path_s=1.0, first_delta_s=1.5)
        )
        stats = _stats([_run(turns).model_dump()])

        assert stats["untimed turns (dropped)"] == 1
        assert stats["turns with a first delta"] == 1
        assert stats["median first delta"] == 1.5

    def test_the_timing_reader_survives_a_cell_that_measured_nothing(self):
        """All crashes: no split to report, and no exception on the way there."""
        stats = _stats([_run([_turn(duration_s=99.0)]).model_dump()])

        assert stats["untimed turns (dropped)"] == 1
        # NOT 0.0. An empty sample has no median, and printing one would put the
        # dropped turns back into the comparison as instant turns — through the
        # summary row this time instead of through the column.
        assert stats["median reply path"] == "not recorded"
        assert stats["worst reply path"] == "not recorded"
        assert stats["arithmetic closes"] == "0/0"
        # `duration_s` is real on a crash, so this one is a reading.
        assert stats["median turn"] == 99.0

    def test_the_probe_treats_an_all_crashed_cell_as_unmeasured(self):
        """`_is_measured` decides which analysis a cell gets.

        A cell carrying the FIELD but no figures belongs with the pre-field
        archives on the regression path, not in a MEASURED block reporting
        medians of an empty sample.

        Honest about its own reach: this half does NOT fail if the Optional change
        is reverted, because `0.0` and `None` are both falsy, so it says nothing
        about `None` in particular. The shape that separates the two predicates is
        in the next test.
        """
        assert not _is_measured(_run([_turn(duration_s=99.0)]))
        assert _is_measured(_run(self._mixed()))

    def test_the_probe_keeps_an_old_drivers_zero_filled_crash_out_of_measured(self):
        """The truthiness in `_is_measured` is a CHOICE, and this is its cost case.

        Tightening it to `reply_path_s is not None` looks like the obvious cleanup
        now that the field is Optional, and every other test in this file stays
        green if you do — a crash written by TODAY's driver is `None`, which both
        predicates reject. The records that separate them were written by the OLD
        driver: a crashed turn there carries `reply_path_s=0.0`, and `is not None`
        admits it. A whole cell of them would then be reported as MEASURED, with
        every median computed over zeros and a `reply path 0% of wall clock` line
        under it.

        No such record is in the archive (all 62 error turns predate the field
        entirely), so this guards a file the bench could still be handed, not one
        it has — which is exactly why a test has to hold it: nothing else would
        notice.
        """
        zero_filled = [
            _turn(duration_s=90.0, reply_path_s=0.0, off_path_s=0.0),
            _turn(duration_s=110.0, reply_path_s=0.0, off_path_s=0.0),
        ]
        assert not _is_measured(_run(zero_filled))
        # And one real turn among them is enough to make the cell measured, which
        # is the same truthiness reading the other way round — the probe then
        # drops the zeros' neighbours by their own `is not None` checks, not here.
        assert _is_measured(_run(zero_filled + [_turn(duration_s=20.0, reply_path_s=18.0)]))

    def test_the_probe_prints_the_dropped_count_and_excludes_them(self, capsys):
        """Whatever the probe drops, it says out loud.

        The count is in the tier header rather than a footnote because every
        share printed under it has the timed turns as its denominator: read
        without it, "reply path 90% of wall clock" looks like a statement about
        the cell when it is a statement about the turns that survived.
        """
        _report_measured([_run(self._mixed())])
        out = capsys.readouterr().out

        assert "1 turns (1 untimed, dropped)" in out
        assert "reply path 18.0s" in out
        # 18/20 of the timed turn's own wall clock. Had the crash been folded in
        # as zeros, the same line would read 7% and the missing 93% would be
        # reported as harness overhead.
        assert "reply path 90%" in out

    def test_the_probe_reports_a_first_delta_only_when_one_exists(self, capsys):
        """Silence is the correct output for every stem published so far."""
        _report_measured([_run(self._mixed())])
        assert "first delta" not in capsys.readouterr().out

        _report_measured(
            [
                _run(
                    [
                        _turn(
                            duration_s=20.0,
                            reply_path_s=18.0,
                            off_path_s=2.0,
                            first_delta_s=3.6,
                        )
                    ]
                )
            ]
        )
        out = capsys.readouterr().out
        assert "first delta (blank-screen wait): median 3.6s on 1/1 turns" in out
        # A PREFIX of the reply path, so it is reported as a share of it and
        # never added to it: 3.6 / 18.0.
        assert "20% of the median reply path" in out


class TestAPooledMedianOverTwoArmsDescribesNoAssistantThatExists:
    """The reader used to pool arms and only WARN about it in its docstring.

    `r26-latency-price` is 64 A1.7 turns beside 64 A2 turns. Pooled, it printed a
    6.15s arm and a 22.85s arm as one 11.50s median — a figure describing neither,
    in the one output the latency question is answered from. The split is opt-in so
    every published pooled figure still reproduces, which makes these tests the
    only thing standing between that and a silent regression to the mixture.
    """

    def _ladder(self) -> list[dict]:
        """A fast tool-free arm and a slow tool-using one, as the archive has them."""
        fast = _run(
            [_turn(duration_s=6.0, reply_path_s=6.0, off_path_s=0.0)],
            arm="A1.7",
        ).model_dump()
        slow = _run(
            [
                _turn(
                    duration_s=30.0,
                    reply_path_s=28.0,
                    off_path_s=2.0,
                    tool_seconds=["anchor:20.0s"],
                )
            ],
            arm="A2",
        ).model_dump()
        return [fast, slow]

    def test_the_pooled_column_declares_itself_a_mixture(self):
        """The actual defect was never the pooling — it was the silence about it."""
        stats = _stats(self._ladder())

        assert stats["arms present"] == "A1.7+A2"
        # And the median it prints is between the arms, belonging to neither.
        assert stats["median reply path"] == 17.0

    def test_splitting_recovers_each_arms_own_figures(self):
        runs = self._ladder()

        assert _arms(runs) == ["A1.7", "A2"]
        fast = _stats(_with_arm(runs, "A1.7"))
        slow = _stats(_with_arm(runs, "A2"))

        assert fast["arms present"] == "A1.7"
        assert slow["arms present"] == "A2"
        assert fast["median reply path"] == 6.0
        assert slow["median reply path"] == 28.0
        # The row that motivated the split: a tool-free arm's `cell wall` and tool
        # totals must not be diluted by the other arm's.
        assert fast["tool calls"] == 0
        assert slow["tool calls"] == 1

    def test_the_arms_come_back_in_ladder_order_not_alphabetical(self):
        """`A1.5` before `A1.7` before `A2` is the order the ablation MEANS.

        Alphabetical sorting happens to agree on these three labels, so a reader
        checking by eye cannot tell the difference — which is why the order is
        asserted against a shuffled input rather than trusted.
        """
        runs = [
            _run([_turn(duration_s=1.0, reply_path_s=1.0, off_path_s=0.0)], arm=arm)
            for arm in ("A2", "A0", "A1.7", "A1", "A1.5")
        ]

        assert _arms([r.model_dump() for r in runs]) == [
            "A0", "A1", "A1.5", "A1.7", "A2"
        ]

    def test_an_unrecognised_arm_is_kept_rather_than_dropped(self):
        """A new ladder rung must not vanish from the table before anyone names it.

        Built as a raw dict, not through `_run`, and that is the honest shape of
        this risk: `RunRecord.arm` is a closed enum, so an arm the ladder does not
        know can only reach the reader from a FILE — an archive written by an older
        or newer driver, which is exactly what this reader is pointed at. Dropping
        it would be the worst failure available, because a reader cannot notice a
        column they were never shown.
        """
        known = _run(
            [_turn(duration_s=2.0, reply_path_s=2.0, off_path_s=0.0)], arm="A2"
        ).model_dump()
        stranger = _run(
            [_turn(duration_s=1.0, reply_path_s=1.0, off_path_s=0.0)], arm="A2"
        ).model_dump()
        stranger["arm"] = "A3"

        assert _arms([known, stranger]) == ["A2", "A3"]
        assert _stats(_with_arm([known, stranger], "A3"))["median reply path"] == 1.0

    def test_a_record_with_no_arm_at_all_is_labelled_rather_than_silently_pooled(self):
        """An archive predating the field must not be filed under a real arm."""
        anonymous = _run(
            [_turn(duration_s=3.0, reply_path_s=3.0, off_path_s=0.0)], arm="A2"
        ).model_dump()
        del anonymous["arm"]

        assert _arms([anonymous]) == ["unknown"]
        assert _stats([anonymous])["arms present"] == "unknown"

    def test_the_split_labels_match_how_the_archive_spells_the_arms(self):
        """`model_dump()` hands over the ENUM; a JSON file hands over a string.

        Both reach this reader — the tests take the first path and the CLI the
        second — and `str(Arm.A1_7)` is `"Arm.A1_7"`. A column headed that still
        splits correctly, so nothing fails; it just stops matching the arm names in
        every report and every row of `rounds.md`, which is the sort of defect that
        gets quoted before it gets noticed.
        """
        dumped = _run(
            [_turn(duration_s=6.0, reply_path_s=6.0, off_path_s=0.0)], arm="A1.7"
        ).model_dump()
        from_json = json.loads(
            _run(
                [_turn(duration_s=6.0, reply_path_s=6.0, off_path_s=0.0)], arm="A1.7"
            ).model_dump_json()
        )

        assert _arms([dumped]) == ["A1.7"]
        assert _arms([from_json]) == ["A1.7"]
        assert _arms([dumped, from_json]) == ["A1.7"], (
            "the two vintages must land in ONE column, not two spellings of one arm"
        )


class TestRetryIsReportedOverItsOwnVintage:
    """A stem older than the retry fields must not read as a stem that ran clean.

    This is `context_render`'s defect on a second field, and it lands harder: the
    whole reason to look at retry is to tell "the deep arm is slow because it
    thinks" from "the deep arm is slow because it failed and waited". A `0` where
    the answer is "nobody measured" settles that question the wrong way, silently.
    `r26-latency-price` — the stem carrying the 1012s worst turn — is exactly this
    vintage.
    """

    def test_a_stem_predating_the_fields_reports_not_recorded_not_zero(self):
        stats = _stats(
            [
                _run(
                    [_turn(duration_s=20.0, reply_path_s=18.0, off_path_s=2.0,
                           retry_seconds=None, retry_count=None)]
                ).model_dump()
            ]
        )

        assert stats["turns recording retry"] == 0
        # The denominator above is honestly zero. Every figure derived from it is
        # not — `sum([])` being 0 is the trap.
        assert stats["retry seconds, total"] == "not recorded"
        assert stats["retry seconds in generation"] == "not recorded"
        assert stats["worst retry seconds"] == "not recorded"
        assert stats["turns that retried"] == "not recorded"

    def test_a_clean_turn_reports_a_real_zero(self):
        """The other half, and the reason `_total` takes a `measured` flag.

        If "measured and clean" printed `not recorded` too, the marker would carry
        no information at all.
        """
        stats = _stats(
            [
                _run(
                    [_turn(duration_s=20.0, reply_path_s=18.0, off_path_s=2.0,
                           retry_seconds=0.0, retry_count=0)]
                ).model_dump()
            ]
        )

        assert stats["turns recording retry"] == 1
        assert stats["turns that retried"] == 0
        assert stats["retry seconds, total"] == 0.0
        assert stats["retry seconds in generation"] == 0.0

    def test_generation_retry_is_the_waste_no_tool_accounts_for(self):
        """The split that answers "slow reply, or failed one?".

        A round's retry is parsed from `tool_retry_seconds`, which shares
        `tool_seconds`' `name:Xs` format — so a parser change on one silently
        moves this figure, and the assertion is written against a turn where the
        two halves DIFFER (6.0 total, 4.0 in a tool) rather than a turn where any
        parse error would still give the right answer.
        """
        stats = _stats(
            [
                _run(
                    [_turn(duration_s=40.0, reply_path_s=38.0, off_path_s=2.0,
                           retry_seconds=6.0, retry_count=3,
                           tool_seconds=["anchor:20.0s"],
                           tool_retry_seconds=["anchor:4.0s"])]
                ).model_dump()
            ]
        )

        assert stats["retry seconds, total"] == 6.0
        assert stats["retry seconds in generation"] == 2.0

    def test_generation_retry_never_goes_negative(self):
        """Mirrors `TurnTiming.generation_retry_seconds`' own clamp.

        The archive's two halves come from one accumulator and its children, so
        this needs a hand-written record to reach — but a negative duration in a
        printed table looks like data, and the reader is where a reader sees it.
        """
        stats = _stats(
            [
                _run(
                    [_turn(duration_s=40.0, reply_path_s=38.0, off_path_s=2.0,
                           retry_seconds=1.0, retry_count=1,
                           tool_seconds=["anchor:20.0s"],
                           tool_retry_seconds=["anchor:9.0s"])]
                ).model_dump()
            ]
        )

        assert stats["retry seconds in generation"] == 0.0


class TestA15sBuildIsReportedBesideItsTurnsNotInsideThem:
    """A1.5's per-turn latency without its build cost is the same work, unbilled.

    The arm is A1 plus a graph prepared BEFORE the conversation, which is exactly
    why it is the "snappy and deep" candidate — and exactly why quoting only its
    turn latency would be the most flattering possible lie about it. The build is a
    full Advisor run over the base sessions, and until 2026-09-11 it was attributed
    to no cell at all: `build_static_context` returned a provenance string that the
    runner printed and dropped.
    """

    def _a15(
        self,
        *,
        build_s: float,
        chars: int,
        scenario: str = "k",
        tier: str = "weak",
        replicate: int = 1,
        branch: str | None = None,
    ):
        run = _run(
            [_turn(duration_s=7.0, reply_path_s=7.0, off_path_s=0.0)],
            tier=tier,
            arm="A1.5",
        )
        run.scenario_key = scenario
        run.replicate = replicate
        run.branch = branch
        run.static_context_build_s = build_s
        run.static_context_chars = chars
        run.static_context_provenance = "perspectives=3 woven=2"
        return run.model_dump()

    def test_the_build_is_reported_at_all(self):
        stats = _stats([self._a15(build_s=615.0, chars=4096)])
        assert stats["static context builds"] == 1
        assert stats["static context build seconds"] == 615.0
        assert stats["static context chars"] == 4096

    def test_one_build_shared_by_eight_cells_is_billed_once(self):
        """The duplication is on purpose and summing it is the trap.

        One build serves every A1.5 cell of a (scenario, tier) — the dump is a
        static artifact, and rebuilding it per replicate would change the arm's
        input between replicates — so all eight cells carry the same seconds. Summed
        naively, 4 replicates x 2 branches would publish an 8x bill for work done
        once, and it would look like the build, not the turns, is where A1.5's
        latency lives.
        """
        cells = [
            self._a15(build_s=615.0, chars=4096, replicate=r, branch=b)
            for r in (1, 2, 3, 4)
            for b in ("wobble_a", "wobble_b")
        ]
        assert len({(c["replicate"], c["branch"]) for c in cells}) == 8
        stats = _stats(cells)
        assert stats["static context builds"] == 1
        assert stats["static context build seconds"] == 615.0

    def test_two_genuinely_different_builds_are_billed_twice(self):
        """The other half of the same rule: a real second build must show up.

        Keyed on (scenario, tier) rather than deduplicated by value, so two builds
        of different scenarios that happened to round to the same seconds stay two.
        """
        stats = _stats(
            [
                self._a15(build_s=615.0, chars=4096, scenario="equity"),
                self._a15(build_s=615.0, chars=2048, scenario="relocation"),
            ]
        )
        assert stats["static context builds"] == 2
        assert stats["static context build seconds"] == 1230.0
        # Max, not sum: chars is the prefill ONE turn pays, and the largest build
        # is the one that bounds it. Summing would describe a prompt nobody sent.
        assert stats["static context chars"] == 4096

    def test_the_build_is_not_folded_into_the_cell_wall(self):
        """`cell wall` is the clock a cell ran on; the build precedes every cell.

        Folding a shared cost into a per-cell figure is how one build gets charged
        eight times — and it would corrupt the one row that is directly comparable
        against A2's.
        """
        stats = _stats([self._a15(build_s=615.0, chars=4096)])
        assert stats["cell wall (run duration_s)"] == 7.0

    def test_an_arm_with_no_build_says_not_recorded_rather_than_zero(self):
        """A1.7 has no build. That is a different fact from a build costing 0s.

        Same rule as the retry rows above, and it matters more here: a `0.00` in
        this row against A1.7 would read as "the pre-built graph is free", which is
        the exact claim A1.5 exists to test.
        """
        stats = _stats(
            [
                _run(
                    [_turn(duration_s=6.0, reply_path_s=6.0, off_path_s=0.0)],
                    arm="A1.7",
                ).model_dump()
            ]
        )
        assert stats["static context builds"] == "not recorded"
        assert stats["static context build seconds"] == "not recorded"
        assert stats["static context chars"] == "not recorded"

    def test_a_failed_build_reports_zero_chars_and_keeps_its_reason(self):
        """0 characters and `failed: ...` are two different findings, both needed.

        A build that raised and a conversation that mapped nothing both leave an
        empty dump and want opposite fixes, so the size cannot be the only record.
        The provenance is printed under the table rather than in it — no cell can
        hold a sentence without truncating the part that matters.
        """
        from e2e.read_turn_timing import _builds

        cell = self._a15(build_s=412.0, chars=0)
        cell["static_context_provenance"] = "failed: RuntimeError: no wheel"
        stats = _stats([cell])
        assert stats["static context chars"] == 0
        assert stats["static context build seconds"] == 412.0
        build = _builds([cell])[("k", "weak")]
        assert build["provenance"] == "failed: RuntimeError: no wheel"

    def test_the_split_keeps_the_build_with_the_arm_that_paid_for_it(self):
        """Pooled, an A1.5 build would be reported against A1.7's turns too."""
        cells = [
            self._a15(build_s=615.0, chars=4096),
            _run(
                [_turn(duration_s=6.0, reply_path_s=6.0, off_path_s=0.0)], arm="A1.7"
            ).model_dump(),
        ]
        assert _arms(cells) == ["A1.5", "A1.7"]
        assert _stats(_with_arm(cells, "A1.5"))["static context build seconds"] == 615.0
        assert (
            _stats(_with_arm(cells, "A1.7"))["static context build seconds"]
            == "not recorded"
        )


class TestReadersHandleTheArchivesMIXEDVintages:
    """A turn can publish a split and still be missing later fields.

    This is the case that breaks readers on REAL data while a synthetic
    same-vintage sample stays green, and it is not rare: of 184 timed turns in
    the archive, 152 predate `retry_seconds`/`retry_count` and 24 predate
    `context_render_s`. So `reply_path_s is not None` does NOT license arithmetic
    on the others — a presence check per field is the actual contract, and
    deleting one raises `TypeError` inside `statistics.median` rather than
    printing a wrong number.

    Both readers therefore get a mixed-vintage sample here. Without it, the
    `or 0.0` and `is not None` guards in the two readers are unpinned: every
    other test in this file feeds them turns written by today's driver, where the
    fields really do arrive together.
    """

    def _old_vintage(self) -> TurnRecord:
        """Shaped like `timing-check-building`: a split, and nothing newer."""
        return _turn(
            duration_s=20.0,
            reply_path_s=18.0,
            off_path_s=2.0,
            context_render_s=None,
            retry_seconds=None,
            retry_count=None,
        )

    def _new_vintage(self) -> TurnRecord:
        return _turn(
            duration_s=30.0,
            reply_path_s=25.0,
            off_path_s=5.0,
            context_render_s=0.5,
            retry_seconds=4.0,
            retry_count=2,
            tool_seconds=["anchor:12.0s"],
            tool_retry_seconds=["anchor:4.0s"],
        )

    def test_the_timing_reader_scopes_each_column_to_its_own_vintage(self):
        stats = _stats(
            [_run([self._old_vintage(), self._new_vintage()]).model_dump()]
        )

        # Both turns published a split, so neither is dropped.
        assert stats["untimed turns (dropped)"] == 0
        assert stats["median reply path"] == 21.5
        # But only one recorded a refresh, and its median is that turn's figure —
        # not 0.25, the average of a measurement and a missing field.
        assert stats["turns recording context_render"] == 1
        assert stats["median context_render"] == 0.5

    def test_the_timing_reader_never_prints_a_zero_for_a_field_it_never_saw(self):
        """The side-by-side is where this row does its damage.

        `timing-check-building` carries `context_render_s` on 0 of 16 turns and
        `timing-after-audit-gather` on 16 of 16, so printing 0.00 in the first
        column against 0.19 in the second reads as a refresh cost the newer build
        INTRODUCED — a regression invented by a missing field, in the one output
        `rounds.md` quotes stem-to-stem comparisons from.
        """
        stats = _stats([_run([self._old_vintage()]).model_dump()])

        assert stats["turns recording context_render"] == 0
        assert stats["median context_render"] == "not recorded"
        # The turn is timed, so nothing was dropped and the split rows are real.
        assert stats["untimed turns (dropped)"] == 0
        assert stats["median reply path"] == 18.0

    def test_the_probe_reports_each_vintage_over_its_own_denominator(self, capsys):
        """The bug this class exists for, at the two sites that had it.

        `context refresh: fired on 72% of turns` was printed where the turns that
        recorded the field say 86%, against a >90% endpoint r26 pre-registered
        and could not test — the missing 20 were zero-filled and counted as
        "did not fire". The retry line had the same shape and a worse ratio.
        """
        _report_measured([_run([self._old_vintage(), self._new_vintage()])])
        out = capsys.readouterr().out

        # 1 of 1 that recorded it, NOT 1 of 2.
        assert "fired on 100% of the 1 turns that recorded it" in out
        # Composition medians come from that same single turn, so the residual is
        # 25.0 - 0.5 - 12.0 and not a mix of two different arithmetics.
        assert "median of 1 turns carrying the field" in out
        assert "generation/residual 12.5s" in out
        # Retry: one turn recorded the fields, and it is the denominator. 4.0/25.0
        # of ITS reply path, not of both turns' 43.0.
        assert "16% of the reply-path seconds of the 1 turns that recorded it" in out
        assert "on 1 of them" in out
        assert "2 attempts retried in total" in out

    def test_neither_reader_completes_the_arithmetic_with_a_term_it_lacks(self):
        """A half-timed turn: reply path published, off path not.

        Not reachable from today's driver — `TurnTiming.off_path_s` is
        non-Optional, so the two arrive together — but it is what an arm that
        timed only its reply path would archive, and it is the shape where
        `off_path_s or 0.0` is worst. Zero-filling it makes the identity
        `duration_s == reply_path_s + off_path_s` EASIER to satisfy: the reader
        would report the invariant holding on a turn where the term it needed was
        never measured.
        """
        half = _turn(duration_s=18.0, reply_path_s=18.0, off_path_s=None)
        stats = _stats([_run([half]).model_dump()])

        # Timed, so not dropped, and its reply path is a real reading.
        assert stats["untimed turns (dropped)"] == 0
        assert stats["median reply path"] == 18.0
        # But unCHECKABLE, so it is not counted as a turn that closed — and not
        # as one that failed to, either.
        assert stats["arithmetic closes"] == "0/0"
        assert stats["median off path"] == "not recorded"

    def test_the_probe_says_so_when_no_turn_recorded_an_off_path(self, capsys):
        """Same shape, at the probe. The split must not read as complete."""
        _report_measured([_run([_turn(duration_s=18.0, reply_path_s=18.0)])])
        out = capsys.readouterr().out

        assert "off path not recorded" in out
        # And the unaccounted seconds surface as harness remainder rather than
        # being silently credited to an off path nobody timed.
        assert "off path 0%" in out

    def test_the_probe_says_so_when_no_turn_recorded_a_retry_account(self, capsys):
        """The else branch is a different claim from "these turns ran clean"."""
        _report_measured([_run([self._old_vintage()])])
        out = capsys.readouterr().out

        assert "retry waste: none recorded" in out
        assert "older than the field" in out
