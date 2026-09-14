"""What the BENCH can see of the graph the A2 arm built, and of the deferral's price.

Three reads were added on 2026-09-14, all of them for the same reason: the
`weave-offturn` round was decided by numbers that the report did not print.
`woven == perspectives` — full weave coverage, which is the whole point of the
deferred drain looping over rounds instead of making one cap-bounded call — had
to be hand-extracted from the run JSON afterwards, and `deferred_wait_s` was
pre-registered as that round's endpoint P3, computed inside the framework, and
read `not recorded` on all 48 A2 turns because it never reached `TurnRecord`.

That is the recurring defect in this archive, and it has now happened four times
(`62244f0`, `2c158bc`, r10's unconstructible hash, and P3): a value computed and
never rendered. Wiring a field into the framework is half of measuring it.

So these tests pin the READ side, and specifically the three ways a read of this
kind degrades quietly:

1. A private helper it borrows gets renamed, and the borrow fails soft.
   `driver._feasibility_rows` deliberately imports `_covered_transitions` and
   `_feasibility_of` FROM `audit_feasibility` rather than reimplementing them,
   because which positions carry a feasibility band (Ac+/Re+, not the
   Transformation) is that tool's decision and a second copy desyncs in silence.
   The cost of borrowing is that a rename turns every row into `import-failed`
   and the endpoint reads 0/6 — indistinguishable from the honest baseline it is
   being compared against. Hence a test on the names.

2. A zero gets counted as a measurement. `graph_summary` is fail-soft: a read
   fault reports an EMPTY graph over a populated one, so `woven == perspectives`
   is satisfied by `0 == 0` and a total read failure scores as FULL coverage.
   That comparison is refused, and this pins the refusal.

3. An absent field gets coerced. `or 0.0` on the reader side reinstates the whole
   bug while the archive stays honest, which is strictly harder to notice than
   the original — the same argument `tests/test_turn_record_timing.py` makes for
   the timing fields, applied to the two fields added the same day.
"""

from __future__ import annotations

import inspect
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from e2e.models import Arm, RunRecord, graph_counts, perspectives_in_summary


def _run(**kw) -> RunRecord:
    """A minimal A2 cell. The five required fields carry no meaning here."""
    return RunRecord(
        arm=Arm.A2,
        tier="weak",
        model="m",
        scenario_key="s",
        replicate=1,
        **kw,
    )


class TestGraphCountsParsesTheWholeLine:
    """One parser for `_graph_summary`'s format, not one per question asked of it."""

    def test_every_count_is_parsed(self):
        counts = graph_counts(
            "perspectives=5 woven=5 transformations=42 decisions=1"
        )
        assert counts == {
            "perspectives": 5,
            "woven": 5,
            "transformations": 42,
            "decisions": 1,
        }

    def test_keys_the_line_omits_are_absent_not_zero(self):
        """The distinction the whole file is about: silent vs. said-to-be-empty.

        Every round archived before `woven` was emitted must read as "the line
        does not say", because `woven=0` would claim the weave ran and wove
        nothing.
        """
        counts = graph_counts("perspectives=5")
        assert counts.get("woven") is None
        assert "woven" not in counts

    def test_an_unparseable_value_is_dropped_rather_than_defaulted(self):
        counts = graph_counts("perspectives=? woven=3")
        assert counts == {"woven": 3}

    def test_none_and_empty_summaries_yield_no_counts(self):
        assert graph_counts(None) == {}
        assert graph_counts("") == {}

    def test_bare_words_are_ignored(self):
        """The line is an audit-trail string, not a strict format."""
        assert graph_counts("graph: perspectives=2 (built)") == {"perspectives": 2}

    def test_perspectives_in_summary_delegates(self):
        """Two parsers for one format is how a warning line and an archived flag
        drift apart and disagree about the same build."""
        source = inspect.getsource(perspectives_in_summary)
        assert "graph_counts(summary)" in source
        assert perspectives_in_summary("perspectives=6 woven=1") == 6
        assert perspectives_in_summary("woven=1") is None
        assert perspectives_in_summary(None) is None


class TestTheFeasibilityBandIsReadFromTheRows:
    """`adopted_pathway_scored` distinguishes unscored from unaudited."""

    def test_a_band_scores(self):
        rec = _run(adopted_pathway_bands=["ab12\tAc+=0.7"])
        assert rec.adopted_pathway_scored is True

    def test_no_rows_at_all_does_not_score(self):
        assert _run().adopted_pathway_scored is False

    def test_each_sentinel_is_refused(self):
        """A row is emitted even when nothing was scored, and a truthiness check
        on the list would read all three of these as a success."""
        for sentinel in ("unscored", "read-failed", "import-failed"):
            rec = _run(adopted_pathway_bands=[f"ab12\t{sentinel}"])
            assert rec.adopted_pathway_scored is False, sentinel

    def test_one_real_band_among_sentinels_scores(self):
        rec = _run(adopted_pathway_bands=["ab12\tunscored", "cd34\tRe+=0.4"])
        assert rec.adopted_pathway_scored is True

    def test_the_default_is_empty_so_old_archives_read_as_unrecorded(self):
        """Every run archived before 2026-09-14 has this field empty. It must
        read as "nobody looked", which is what the report's own `not recorded`
        branch then prints with its own denominator."""
        assert _run().adopted_pathway_bands == []


class TestTheBorrowedHelpersStillExist:
    """The coupling `_feasibility_rows` accepts on purpose, pinned.

    Renaming either helper in `audit_feasibility` makes the bench read
    `import-failed` on every cell, and `import-failed` is scored as unrecorded —
    which is exactly the 0/6 baseline the endpoint is measured against. The
    failure would therefore look like a null result. This test converts that
    into a red test in the same commit as the rename.
    """

    def test_the_two_helpers_are_importable_with_the_expected_shapes(self):
        from dialectical_framework.agents.orchestrator.tools.audit_feasibility import (
            _covered_transitions,
            _feasibility_of,
        )

        # `_covered_transitions(tr) -> [(label, transition)]`, one arg.
        assert len(inspect.signature(_covered_transitions).parameters) == 1
        # `_feasibility_of(transition) -> (score, why)`, one arg, pair back.
        assert len(inspect.signature(_feasibility_of).parameters) == 1

    def test_the_driver_borrows_rather_than_reimplements(self):
        """Which positions carry a band is `audit_feasibility`'s call.

        Ac+/Re+ is a theory decision (Ac+ without Re+ degenerates to Ac-), so a
        copy of the position list in the bench would keep scoring the old poles
        after the theory moved, and agree with itself while doing it.
        """
        from e2e.driver import E2EDriver

        source = inspect.getsource(E2EDriver._feasibility_rows)
        assert "_covered_transitions" in source
        assert "_feasibility_of" in source
        # The position list must not be COPIED. Checked against the code with
        # the docstring removed, because that docstring cites the name on
        # purpose ("which positions count is `_COVERED_POSITIONS`") and a naive
        # substring check fails on the explanation of why the copy is absent.
        # (`inspect.getdoc` dedents, so replacing it out of the source does
        # not match the indented original -- partition on the delimiter.)
        _doc, _, body = source.partition('"""')[2].partition('"""')
        assert "_COVERED_POSITIONS" not in body, "position list copied, not borrowed"
        assert '"Ac+"' not in body and '"Re+"' not in body, "poles hardcoded"


class TestTheReportRefusesToCountZeroAsCoverage:
    """`0 == 0` is not full weave coverage; `0 of 0` is not a measurement."""

    def test_an_empty_graph_is_not_full_coverage(self):
        from e2e import report

        source = inspect.getsource(report.render_report)
        assert "elif pp == 0:" in source, "the 0==0 guard is gone"
        assert '"none built"' in source
        # And it must be checked BEFORE the equality, or it never runs.
        assert source.index("elif pp == 0:") < source.index("elif woven == pp:")

    def test_an_absent_field_prints_not_recorded_with_its_denominator(self):
        from e2e import report

        source = inspect.getsource(report.render_report)
        assert "deferred weave wait: not recorded" in source
        assert "adopted pathway carries a feasibility band: not recorded" in source
        # No coercion anywhere near the wait: a zero says the deferral is free
        # and an absent field says nobody checked, and those are opposite.
        assert "t.deferred_wait_s or 0" not in source

    def test_an_untimed_round_is_distinguished_from_an_unrecorded_field(self):
        """`0 of 0 timed turn(s)` reads as "the wait was absent" when it means
        "this round has no timing lane at all"."""
        from e2e import report

        source = inspect.getsource(report.render_report)
        assert "deferred weave wait: n/a" in source

    def test_the_a2_table_says_so_when_no_summary_was_recorded(self):
        """Dropping the block when the field is absent is the same defect as
        printing 0.00 for it: a reader cannot then tell an unrecorded graph from
        a round with no A2 arm."""
        from e2e import report

        source = inspect.getsource(report.render_report)
        assert "A2 graph built: not recorded" in source

    def test_the_table_is_per_cell_not_per_session(self):
        """A wobble cell runs two sessions against ONE graph, so a per-session
        listing prints every cell twice and doubles n — and n is what the Fisher
        exact on this endpoint is computed from."""
        from e2e import report

        source = inspect.getsource(report.render_report)
        assert "A2 cell(s)" in source
        assert "session(s)" not in source.split("A2 graph built")[1][:2000]
