"""Does a recorded rationale assert the objection it survived is VOID?

    poetry run python tests/bench/probe_rationale_integrity.py
    poetry run python tests/bench/probe_rationale_integrity.py --show
    poetry run python tests/bench/probe_rationale_integrity.py --forensics

Free — reads the saved archive, calls no model.

The failure this counts: the person argues a risk away over four rebuttals, the
arm commits anyway, and the RECORD it writes says the risk "doesn't hold
empirically" rather than "was accepted at this cost". Carrying a conceded
objection forward as fact is worse than dropping it, because the graph then
looks like evidence.

WHY THIS SCRIPT EXISTS, AND THE LESSON IN IT
============================================
The rate that motivated the fourth `DecisionCoherenceCheck` (2026-08-13) was
3 of 12 A2 decisions on this lane — and it was a PROXY. `driver._read_decisions`
did not capture the rationale text or `Decision.validation` at the time, so the
count had to be taken over the rendered `## Decision` blocks in the next
session's carryover dump. A dump-side proxy cannot see what landed in the GRAPH,
which is the entire distinction the failure is about: the dump shows what the
assistant chose to render, and the check under test is about what was stored.

General form, recorded in the systemic map: **before writing a prompt rule from a
measured rate, check the measurement can see the thing the rule changes.**

So this probe reports the two sides side by side and never merges them:

  DUMP    — the pre-2026-08-14 proxy, available for the whole archive. Reads
            `## Decision` blocks out of `SessionRecord.carryover_in`.
  CAPTURED— `RunRecord.decision_rationales` / `.decision_verdicts`, read off the
            graph by `driver._read_decisions`. Empty for every run recorded
            before the capture landed, and that is printed as "predates
            capture", never as zero. A rate of 0/0 rendered as 0% is the same
            averaging-in mistake `probe_five_fixes` refuses for its semantic
            fixes.

WHAT IT FOUND (dump side, whole archive)
========================================
4 of 12 A2 decisions on `cofounder_ladder_return` assert the objection is void;
0 of 80 on every other scenario. The failure is SCENARIO-SPECIFIC — it needs a
person who argues a risk down and an arm that commits anyway, which is exactly
what this lane scripts and no other lane does. A run that spread the count over
all scenarios would have reported 4/92 (4%) and concluded there was nothing to
fix.

**None of the four was flagged FOR THIS REASON.** Three passed outright; the
fourth (`91afedb`, the fabricated Vasquez & Lindqvist citation) failed — but on
an unrelated criterion, an accepted cost its rationale never addressed, with the
verdict's reasons naming the coerced buyout and never the refuted risk. So the
pre-fix audit's miss is 4 of 4, and one of them shows the audit CAN fire on a
record it still misreads. Worth stating precisely, because "every one passed"
(the first phrasing) is the kind of claim that gets checked.

A SECOND COUNTING BUG, FOUND WHILE PROMOTING THIS SCRIPT (2026-08-14)
=====================================================================
Originally reported as 6 of 24 against 0 of 160 — exactly double. The ad-hoc
counter globbed `results/*.json` and the archive keeps a `<stem>-runs.json`
sidecar holding a duplicate copy of every run, so each decision was counted
twice. The rate (25%), the scenario-locality and therefore the fix all stand
unchanged; only the denominators were wrong, and every site quoting them was
corrected.

Which is the reason this file exists rather than another `/tmp` one-liner:
`_stems()` here carries the `-runs`/`-rejudged`/`smoke` exclusion that
`probe_five_fixes` already had, and a throwaway script that re-implements
archive loading inherits none of the loader's fixes. The cost/validation
cross-tab below escaped the bug only because it happened to deduplicate by
hash.

And the audit's own agreement was already visible in the dump: of the decisions
rendered with NO accepted cost, 11 of 12 nonetheless carried
`Validation: passed` (against 41 of 80 with a cost). The pre-fix check was
clearing exactly the records this failure produces — which is why a fourth
coherence criterion was added rather than the existing three being retuned.

WHAT IT CANNOT SEE
==================
Voidness is matched by regex over the rationale's first sentence. It catches the
blunt forms ("doesn't hold", "is not material", "systematically overweighted")
and misses a rationale that reaches the same place by implication. It is a
FLOOR, not a rate: a miss is a miss, a hit is real. The `--show` flag prints
every hit with its verdict so the floor stays auditable by eye rather than
trusted.
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

BENCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BENCH_DIR.parent))

from bench.models import RunRecord  # noqa: E402
from bench.report import load_records  # noqa: E402

RESULTS = BENCH_DIR / "results"

#: A rationale asserting the objection is VOID — disproven, immaterial, not
#: real — as opposed to outweighed. "Outweighed at a cost" is the CORRECT shape
#: and must never match: the whole point of a decision record is that it names
#: what it is paying. Deliberately blunt; see "WHAT IT CANNOT SEE".
_VOID = re.compile(
    r"doesn'?t hold"
    r"|does not hold"
    r"|is ?n[o']?t material"
    r"|is not material"
    r"|is ?n[o']?t a (real|material|genuine)"
    r"|is not a (real|material|genuine)"
    r"|overweighted"
    r"|no real risk"
    r"|not a real risk"
    # Found by eye with --forensics, AFTER the first count: r2's rationale says
    # the customer risk "is not a factor" and cleared the audit, and the regex
    # missed it. Kept as evidence that the floor moves when someone reads the
    # hits — which is what --forensics is for.
    r"|is ?n[o']?t a factor"
    r"|is not a factor"
    r"|no significant .{0,30}effect"
    r"|doesn'?t exist"
    r"|does not exist"
    r"|disproven"
    r"|empirically (wrong|false)"
    r"|(is ?n[o']?t|not) supported by",
    re.I,
)

#: One rendered `## Decision [[hash]]` block, up to the next `## ` header.
_BLOCK = re.compile(r"^## Decision \[\[(\w+)\]\].*?(?=^## |\Z)", re.M | re.S)

#: The rationale line inside a rendered block ("Why: ...", "Why now: ...").
_WHY = re.compile(r"^Why[^:]*:\s*(.*)$", re.M)


def _stems() -> list[str]:
    return sorted(
        p.stem
        for p in RESULTS.glob("*.json")
        if not p.stem.endswith(("-runs", "-rejudged")) and not p.stem.startswith("smoke")
    )


def _runs() -> list[RunRecord]:
    runs: list[RunRecord] = []
    for stem in _stems():
        payload = load_records(RESULTS / f"{stem}.json")
        for raw in payload.get("runs", []):
            try:
                runs.append(RunRecord.model_validate(raw))
            except Exception:  # noqa: BLE001 - an old schema is skipped, not fatal
                continue
    return runs


class _Dump:
    """The pre-capture proxy: decisions as RENDERED into a carryover dump.

    Keyed by decision hash across the whole archive, because one decision is
    re-rendered into every later session of its run and would otherwise be
    counted several times.
    """

    def __init__(self) -> None:
        #: hash -> (rationale, validation, has_cost, scenario)
        self.rows: dict[str, tuple[str, str, bool, str]] = {}

    def add(self, run: RunRecord) -> None:
        for session in run.sessions:
            for match in _BLOCK.finditer(session.carryover_in or ""):
                block = match.group(0)
                why = _WHY.search(block)
                if re.search(r"^Validation: passed", block, re.M):
                    validation = "passed"
                elif re.search(r"^Validation: failed", block, re.M):
                    validation = "failed"
                else:
                    validation = "none"
                self.rows[match.group(1)] = (
                    why.group(1) if why else "",
                    validation,
                    "accepted cost:" in block,
                    run.scenario_key,
                )


def _dump_side(runs: list[RunRecord], *, show: bool) -> None:
    dump = _Dump()
    for run in runs:
        if run.arm.value == "A2":
            dump.add(run)

    per_scenario: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for why, _validation, _cost, scenario in dump.rows.values():
        per_scenario[scenario][0] += 1
        if _VOID.search(why):
            per_scenario[scenario][1] += 1

    print("DUMP SIDE — A2 decisions as rendered into a later session's artifact")
    print(f"  distinct decisions across {len(_stems())} saved runs: {len(dump.rows)}")
    print(f"  {'scenario':34}{'decisions':>10}{'void-assertions':>18}")
    for scenario, (total, void) in sorted(per_scenario.items()):
        flag = "   <-- the lane" if void else ""
        print(f"  {scenario:34}{total:>10}{void:>18}{flag}")

    # The audit's pre-fix agreement: did "no accepted cost" predict a flag?
    table: dict[tuple[bool, str], int] = defaultdict(int)
    for _why, validation, has_cost, _scenario in dump.rows.values():
        table[(has_cost, validation)] += 1
    print("\n  Did the pre-fix audit already see it? (rendered blocks only)")
    print(f"  {'accepted cost named':>21}{'validation':>12}{'decisions':>11}")
    for (has_cost, validation), count in sorted(table.items()):
        print(f"  {str(has_cost):>21}{validation:>12}{count:>11}")

    if show:
        print("\n  Every void-assertion, so the regex floor stays auditable:")
        for short_hash, (why, validation, has_cost, scenario) in sorted(
            dump.rows.items()
        ):
            if not _VOID.search(why):
                continue
            print(f"    [[{short_hash}]] {scenario} validation={validation} cost={has_cost}")
            print(f"        {why[:220]}")


def _captured_side(runs: list[RunRecord], *, show: bool) -> None:
    """The same count over what `driver._read_decisions` read off the GRAPH."""
    with_capture = [r for r in runs if r.decision_rationales or r.decision_verdicts]
    print("\nCAPTURED SIDE — rationale text and verdict read off the graph")
    if not with_capture:
        print(
            "  0 saved runs carry captured rationales: the whole archive predates\n"
            "  capture (2026-08-14). NOT reported as a rate of 0 — there is no\n"
            "  denominator. Re-run the lane to populate this side."
        )
        return

    total = void = audited = flagged = 0
    hits: list[tuple[str, str]] = []
    for run in with_capture:
        for entry in run.decision_rationales:
            short_hash, _, why = entry.partition(": ")
            total += 1
            if _VOID.search(why):
                void += 1
                hits.append((f"{run.scenario_key} r{run.replicate} [[{short_hash}]]", why))
        for verdict in run.decision_verdicts:
            if not verdict.endswith(":none"):
                audited += 1
        flagged += len(run.audit_flagged_decisions)

    print(f"  runs with capture: {len(with_capture)} of {len(runs)}")
    print(f"  rationales read off the graph: {total}")
    print(f"  asserting the objection is void: {void}")
    print(f"  decisions whose audit ran: {audited}")
    print(f"  decisions the audit FLAGGED: {flagged}")
    if audited and void and not flagged:
        print(
            "  !! the audit ran, the void assertions are there, and it flagged\n"
            "     none of them — the fourth coherence criterion is not firing."
        )
    if show:
        for label, why in hits:
            print(f"    {label}\n        {why[:220]}")


def _forensics(runs: list[RunRecord], stem: str) -> None:
    """Print one lane's whole Decision block, its grounds, and the commit turn.

    The counts above say how often; this says what it looked like, which is what
    every fix to the ceremony was actually written against. Reading three of
    these is how the "no accepted cost" pattern was noticed at all — a rate alone
    would have named the behaviour without suggesting where the audit's blind
    spot was.
    """
    subject = [
        r
        for r in runs
        if r.arm.value == "A2" and r.scenario_key == "cofounder_ladder_return"
    ]
    if not subject:
        print(f"\nFORENSICS: no A2 ladder-return runs saved (looked for {stem})")
        return
    print(f"\nFORENSICS — {len(subject)} A2 cells on the ladder-return lane")
    for run in sorted(subject, key=lambda r: r.replicate):
        why_hit = any(
            _VOID.search(entry.partition(": ")[2]) for entry in run.decision_rationales
        )
        print("=" * 70)
        print(f"r{run.replicate}   void-assertion in captured rationale: {why_hit}")
        print(f"  accepted_cost_grounds : {run.accepted_cost_grounds or '(none)'}")
        print(
            f"  adopted_pathway_grounds: "
            f"{[g[:88] for g in run.adopted_pathway_grounds] or '(none)'}"
        )
        for verdict in run.decision_verdicts:
            print(f"  verdict               : {verdict}")
        for entry in run.decision_rationales:
            print(f"  rationale             : {entry[:400]}")
        # The rendered block, for runs predating capture — the only view there is.
        returning = run.session("followup")
        if returning and not run.decision_rationales:
            for match in _BLOCK.finditer(returning.carryover_in or ""):
                print("  --- as RENDERED into the returning session ---")
                for line in match.group(0).splitlines()[:14]:
                    print(f"    {line}")
        # What the person actually said on the commit beat, which is the pressure
        # the rationale was written under.
        ladder = run.session("ladder")
        for turn in ladder.turns if ladder else []:
            if turn.tag == "commit":
                print(f"  the person, on `commit`: {turn.user[:300]}")
                print(f"  tools called           : {turn.tool_calls}")


def main() -> int:
    show = "--show" in sys.argv
    runs = _runs()
    a2 = [r for r in runs if r.arm.value == "A2"]
    print(f"{len(runs)} saved runs, {len(a2)} of them A2 (only A2 records decisions)\n")
    _dump_side(runs, show=show)
    _captured_side(runs, show=show)
    if "--forensics" in sys.argv:
        _forensics(runs, "cofounder_ladder_return")
    print(
        "\nThe two sides are never merged. The dump is what the assistant chose to\n"
        "RENDER; the captured side is what the graph STORES, and the coherence\n"
        "check under test is about the latter. Pass --show to read the hits,\n"
        "--forensics to read the lane's decision blocks and commit turns whole."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
