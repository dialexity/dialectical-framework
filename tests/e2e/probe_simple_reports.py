"""Does a person's REPORT of a situation classify SIMPLE — and which lever moves it?

WHY THIS EXISTS
===============
`tests/e2e/probe_tetrad_quality.py`, set B (2026-09-30): 3 of 20 fresh utterances
classified SIMPLE — all three the person REPORTING a situation ("My father refuses
to stop driving and he's eighty-four") — and each became a mechanical negation on
the anchor path (HS hardcoded 1.0, no ladder, no potential) whose tetrad failed the
coherence check. `probe_classifier_stability.py` had already shown the boundary
does not FLIP (0 of 47 on Haiku; 0 of 100 on Sonnet 5 over set A), so this is not
instability: it is the RULE. "Verifiable by direct observation" is true of a
report, and on the anchor path the person's report IS their position.

Two levers, and they have different blast radii:
  `wording`  one sentence added to the classifier's COMPLEX definition — changes
             the classifier for EVERY caller, including `ingest` over documents,
             where "the server refuses connections" is a fact and should stay one.
  `framed`   the production prompts untouched; the caller passes context saying
             the statement is the person's own position — a lever only the anchor
             path would pull.

THE POPULATION (fixed before any statement was classified, 2026-10-01)
=====================================================================
Operational definitions, written first:
  REPORT  A first-person account of a situation the speaker is IN — another
          person's behaviour toward them or a standing state of affairs in their
          own life — phrased as a declarative FACT. No "should", no proposed
          action, no stated cause-and-effect. Includes set B's three verbatim.
  FACT    Verifiable by inspection, with no person holding a stake in it and no
          dynamics: a count, a time, a place, a property. The over-correction
          guard — a lever that moves these has broken the classifier.
  COURSE  A named option / course of action, or an explicit causal claim. Must
          stay COMPLEX under every arm. None repeats an example printed in the
          classifier's own prompt (that would be reading the answer back).

20 per stratum × 3 readings × 3 arms = 540 classifications, on the configured
model. Every reading is persisted (statement, arm, is_simple, meaning URI,
reasoning); the script is resumable and each invocation stops launching work at
its `--budget`.

    poetry run python tests/e2e/probe_simple_reports.py --arm prod
    poetry run python tests/e2e/probe_simple_reports.py --arm wording
    poetry run python tests/e2e/probe_simple_reports.py --arm framed
    poetry run python tests/e2e/probe_simple_reports.py --report

Database-free: `StatementClassification.resolve` writes nothing.
"""

from __future__ import annotations

import argparse
import asyncio
import collections
import json
import time
from pathlib import Path
from typing import Any, Optional

OUT = (
    Path(__file__).resolve().parent
    / "results"
    / "tetrad_quality"
    / "simple_reports-20261001.json"
)

READINGS = 3
ARMS = ("prod", "wording", "framed")

#: The ONE sentence of the `wording` arm. Positive specification plus one
#: example, in the same form as the prompt's existing named-options clause. The
#: example is deliberately NOT a member of the population.
WORDING_SENTENCE = (
    "A person's account of a situation they are in — someone's behaviour toward "
    "them, a relationship pattern, a standing conflict — is likewise COMPLEX: it "
    "is a stance held inside a system of people and stakes, not a fact to verify "
    '("My landlord ignores every repair request I send").'
)

#: The context the `framed` arm passes as `text`, production prompts untouched.
FRAME_TEXT = "This is a position the person holds about their own situation."

REPORT = "REPORT"
FACT = "FACT"
COURSE = "COURSE"
FIRST_PERSON_FACT = "FIRST_PERSON_FACT"

POPULATION: dict[str, list[str]] = {
    REPORT: [
        # set B's three, verbatim
        "My daughter wants to drop out of university to travel.",
        "My father refuses to stop driving and he's eighty-four.",
        "My sister expects me to host every family holiday.",
        # family
        "My mother calls me five times a day.",
        "My husband makes every big purchase without telling me.",
        "My teenage son hasn't spoken to me in two weeks.",
        "My brother still lives with our parents at forty.",
        # work
        "My manager takes credit for my work in every meeting.",
        "My business partner has stopped answering my messages.",
        "My team lead assigns me the tasks nobody else wants.",
        "My colleague copies my boss on every email she sends me.",
        "My employees come to me for every small decision.",
        # money
        "My wife and I keep separate bank accounts.",
        "My parents still pay my rent and I'm thirty-two.",
        "My ex-husband pays child support late every month.",
        "My co-founder draws a bigger salary than I do.",
        # health
        "My doctor wants me to start medication for my blood pressure.",
        "My mother refuses to see anyone about her memory.",
        "My partner still smokes in the house and I have asthma.",
        "My best friend has cancelled on me four times in a row.",
    ],
    FACT: [
        "The warehouse has 12 loading docks.",
        "The meeting is on Tuesday.",
        "Light travels faster than sound.",
        "The invoice total is 4,200 euros.",
        "The office is on the third floor.",
        "The report has 42 pages.",
        "The server runs Ubuntu 22.04.",
        "The train leaves at 7:15.",
        "Paris is the capital of France.",
        "The contract was signed on 3 March.",
        "The file is 2 megabytes.",
        "The API returns JSON.",
        "The store closes at 9 pm.",
        "The table has six columns.",
        "The battery is at 80 percent.",
        "The building has two elevators.",
        "The password must be at least 12 characters.",
        "The flight number is LX 318.",
        "The database has 14 tables.",
        "The conference lasts three days.",
    ],
    COURSE: [
        "Accept the relocation package.",
        "Remote work is killing our culture.",
        "Rewrite the backend in Rust.",
        "Hire a second salesperson.",
        "Move the family to Lisbon.",
        "Raise prices by ten percent.",
        "Outsourcing support erodes customer trust.",
        "Micromanagement destroys initiative.",
        "Sell the house and rent.",
        "Go back to university at forty.",
        "Cut the product line in half.",
        "Transparency builds trust in teams.",
        "Take out a loan to expand.",
        "Frequent releases reduce risk.",
        "Switch the kids to a private school.",
        "Open-source the core library.",
        "Strict deadlines sharpen focus.",
        "Merge the two departments.",
        "Quit sugar entirely.",
        "Shared ownership spreads accountability thin.",
    ],
    # FOLLOW-UP STRATUM (fixed 2026-10-01, before any of it was classified, and
    # after the first three strata had run). The first run's FACT stratum is all
    # third-person ("The server runs..."), so it could not show the one
    # over-correction the `wording` sentence invites: a first-person or
    # possessive statement that is a plain verifiable fact — what a document or
    # a status note contains, and what `ingest` classifies all day.
    # Rule: subject is my/our/we/I; the content is checkable by inspection; NO
    # stance toward another party and no person behaving toward the speaker.
    # The first eight deliberately wear a REPORT's surface form (a subject plus
    # a present-tense verb about behaviour — "refuses", "restarts", "drops"),
    # because that resemblance is exactly where over-correction would show.
    # Run under `prod` and `wording` only.
    FIRST_PERSON_FACT: [
        # REPORT-shaped surface, machine or process as the actor
        "Our server refuses connections on port 443.",
        "Our build server restarts every night.",
        "My laptop refuses to wake from sleep.",
        "Our printer jams on every double-sided job.",
        "My phone drops calls in the basement.",
        "Our nightly backup fails on the first of every month.",
        "My car stalls when the engine is cold.",
        "Our website logs users out after ten minutes.",
        # plain possessive / first-person facts
        "My team has six people.",
        "We shipped version 2.3 on Monday.",
        "Our office is on the fourth floor.",
        "I joined the company in March.",
        "Our fiscal year ends in June.",
        "I have two monitors on my desk.",
        "We use PostgreSQL for the main database.",
        "My contract runs until December.",
        "Our warehouse is in Rotterdam.",
        "I work from home on Fridays.",
        "We have 340 paying customers.",
        "Our API has a rate limit of 100 requests per minute.",
    ],
}

_SET_B_THREE = POPULATION[REPORT][:3]

#: Strata an arm is run on. The follow-up stratum was asked for under `prod`
#: and `wording` only; `framed` measurably did nothing on REPORT and is not
#: spent on it.
_ARM_STRATA: dict[str, tuple[str, ...]] = {
    "prod": (REPORT, FACT, COURSE, FIRST_PERSON_FACT),
    "wording": (REPORT, FACT, COURSE, FIRST_PERSON_FACT),
    "framed": (REPORT, FACT, COURSE),
}


# --- population checks (run on every invocation; cheap) ------------------------


def _check_population() -> None:
    for stratum, items in POPULATION.items():
        assert len(items) == 20, (stratum, len(items))
        assert len(set(items)) == 20, f"duplicate in {stratum}"
    everything = [s for items in POPULATION.values() for s in items]
    assert len(set(everything)) == 80
    # The wording example must not be a population member (or a near copy).
    assert not any("landlord" in s.lower() for s in everything)
    # No item may be an example the classifier's own prompt prints.
    from dialectical_framework.concerns import statement_classification as sc

    for s in everything:
        assert s.rstrip(".") not in sc.SYSTEM_PROMPT, f"in the prompt already: {s}"
    # The follow-up stratum's rule: a first-person or possessive subject.
    for s in POPULATION[FIRST_PERSON_FACT]:
        assert s.split()[0] in ("My", "Our", "We", "I"), s


# --- persistence ---------------------------------------------------------------


def _load() -> dict[str, Any]:
    if OUT.exists():
        return json.loads(OUT.read_text())
    return {"readings": {}, "errors": []}


def _save(state: dict[str, Any]) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(state, indent=1, ensure_ascii=False))


def _key(arm: str, stratum: str, statement: str) -> str:
    return f"{arm}|{stratum}|{statement}"


# --- the arms ------------------------------------------------------------------


class _WordingPatch:
    """The `wording` arm: the one sentence, at BOTH sites where the prompt
    already states its sibling rule (the named-options clause) — the system
    prompt's COMPLEX list and the user prompt's clarifying paragraph. Nothing
    under `src/` is edited; both anchors are asserted so a drifted prompt fails
    loudly instead of running an unpatched arm under the patched arm's name."""

    _SYSTEM_ANCHOR = '- Examples: "Trust", "Data consistency"'
    _USER_ANCHOR = "even when phrased as a bare imperative."

    def __enter__(self) -> "_WordingPatch":
        from dialectical_framework.concerns import statement_classification as sc

        self._sc = sc
        self._system = sc.SYSTEM_PROMPT
        self._method = sc.StatementClassification._classification_prompt
        assert sc.SYSTEM_PROMPT.count(self._SYSTEM_ANCHOR) == 1
        sc.SYSTEM_PROMPT = sc.SYSTEM_PROMPT.replace(
            self._SYSTEM_ANCHOR, f"- {WORDING_SENTENCE}\n{self._SYSTEM_ANCHOR}"
        )
        original = self._method
        anchor = self._USER_ANCHOR

        def patched(instance: Any) -> str:
            prompt = original(instance)
            assert prompt.count(anchor) == 1
            return prompt.replace(anchor, f"{anchor} {WORDING_SENTENCE}")

        sc.StatementClassification._classification_prompt = patched
        return self

    def __exit__(self, *exc: Any) -> None:
        self._sc.SYSTEM_PROMPT = self._system
        self._sc.StatementClassification._classification_prompt = self._method


async def _read(arm: str, statement: str, sem: asyncio.Semaphore) -> dict[str, Any]:
    from dialectical_framework.concerns.statement_classification import \
        StatementClassification

    async with sem:
        started = time.monotonic()
        try:
            result = await StatementClassification().resolve(
                statement=statement, text=FRAME_TEXT if arm == "framed" else ""
            )
        except Exception as exc:  # noqa: BLE001 — a probe records, never hides
            return {"error": repr(exc)[:300]}
        return {
            "is_simple": bool(result.is_simple),
            "meaning": result.meaning,
            "reasoning": result.classification_reasoning,
            "taxonomy_reasoning": result.taxonomy_reasoning,
            "seconds": round(time.monotonic() - started, 1),
        }


async def _run_arm(arm: str, budget_s: float) -> None:
    state = _load()
    readings: dict[str, list] = state["readings"]
    todo: list[tuple[str, str]] = []
    for stratum in _ARM_STRATA[arm]:
        for statement in POPULATION[stratum]:
            have = len(readings.get(_key(arm, stratum, statement), []))
            todo.extend((stratum, statement) for _ in range(READINGS - have))
    total = 20 * READINGS * len(_ARM_STRATA[arm])
    print(f"arm {arm}: {len(todo)} readings to make", flush=True)
    if not todo:
        return
    sem = asyncio.Semaphore(6)
    deadline = time.monotonic() + budget_s
    chunk = 18
    for start in range(0, len(todo), chunk):
        if time.monotonic() > deadline:
            print(f"  budget reached with {len(todo) - start} left — rerun to resume",
                  flush=True)
            break
        batch = todo[start:start + chunk]
        results = await asyncio.gather(*(_read(arm, s, sem) for _st, s in batch))
        for (stratum, statement), reading in zip(batch, results):
            if "error" in reading:
                state["errors"].append({"arm": arm, "statement": statement, **reading})
                continue
            readings.setdefault(_key(arm, stratum, statement), []).append(reading)
        _save(state)
        done = sum(len(v) for k, v in readings.items() if k.startswith(f"{arm}|"))
        print(f"  {done}/{total} persisted", flush=True)


# --- the report ----------------------------------------------------------------


def _wilson(k: int, n: int) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    z = 1.96
    p = k / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half = z * ((p * (1 - p) / n + z**2 / (4 * n**2)) ** 0.5) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def _branch(meaning: Optional[str]) -> str:
    from dialectical_framework.concerns.statement_classification import \
        parse_meaning_uri

    if not meaning or meaning.startswith("dx://taxonomy/Simple"):
        return "SIMPLE"
    domain, _category, branch, leaf = parse_meaning_uri(meaning)
    family = "Elements" if "/Elements(" in meaning else "System"
    return f"{family}({domain})/{branch}/{leaf}"


def _report() -> None:
    state = _load()
    readings: dict[str, list] = state["readings"]
    print(f"file: {OUT}")
    print(f"errors recorded: {len(state['errors'])}")
    print("\nSIMPLE rate per arm x stratum (readings), Wilson 95%:")
    for arm in ARMS:
        for stratum in _ARM_STRATA[arm]:
            rs = [r for s in POPULATION[stratum]
                  for r in readings.get(_key(arm, stratum, s), [])]
            k = sum(1 for r in rs if r["is_simple"])
            lo, hi = _wilson(k, len(rs))
            flips = sum(
                1 for s in POPULATION[stratum]
                if len({r["is_simple"] for r in readings.get(_key(arm, stratum, s), [])}) > 1
            )
            ever = sum(
                1 for s in POPULATION[stratum]
                if any(r["is_simple"] for r in readings.get(_key(arm, stratum, s), []))
            )
            print(f"  {arm:8s} {stratum:17s} {k:2d}/{len(rs):2d} "
                  f"({100 * k / max(len(rs), 1):3.0f}%, {100 * lo:.0f}-{100 * hi:.0f}%)  "
                  f"statements ever SIMPLE {ever}/20, flipping {flips}/20")
    print("\nset B's three, SIMPLE readings per arm:")
    for s in _SET_B_THREE:
        cells = []
        for arm in ARMS:
            rs = readings.get(_key(arm, REPORT, s), [])
            cells.append(f"{arm} {sum(r['is_simple'] for r in rs)}/{len(rs)}")
        print(f"  {'  '.join(cells)}  «{s}»")
    print("\nREPORT statements, SIMPLE readings (prod / wording / framed):")
    for s in POPULATION[REPORT]:
        cells = []
        for arm in ARMS:
            rs = readings.get(_key(arm, REPORT, s), [])
            cells.append(f"{sum(r['is_simple'] for r in rs)}/{len(rs)}")
        print(f"  {' '.join(cells)}  «{s}»")
    for arm in ("wording", "framed"):
        moved = [s for stratum in (FACT,) for s in POPULATION[stratum]
                 if any(not r["is_simple"] for r in readings.get(_key(arm, stratum, s), []))]
        print(f"\nFACT statements {arm} moved to COMPLEX at least once ({len(moved)}):")
        for s in moved:
            rs = readings.get(_key(arm, FACT, s), [])
            print(f"  {sum(not r['is_simple'] for r in rs)}/{len(rs)} COMPLEX  «{s}»")
    print("\nFIRST_PERSON_FACT, COMPLEX readings (prod / wording) and wording's home:")
    for s in POPULATION[FIRST_PERSON_FACT]:
        cells = []
        for arm in ("prod", "wording"):
            rs = readings.get(_key(arm, FIRST_PERSON_FACT, s), [])
            cells.append(f"{sum(not r['is_simple'] for r in rs)}/{len(rs)}")
        w = [r for r in readings.get(_key("wording", FIRST_PERSON_FACT, s), [])
             if not r["is_simple"]]
        home = _branch(w[0]["meaning"]) if w else ""
        print(f"  {' '.join(cells)}  «{s}»  {home}")
    for arm in ARMS:
        homes = collections.Counter()
        families = collections.Counter()
        for s in POPULATION[REPORT]:
            for r in readings.get(_key(arm, REPORT, s), []):
                if not r["is_simple"]:
                    b = _branch(r["meaning"])
                    homes[b.split("/")[1]] += 1
                    families[b.split("/")[0]] += 1
        print(f"\nREPORT readings classified COMPLEX under {arm}: "
              f"families {dict(families)}; branches {dict(homes.most_common())}")
    print("\nREPORT homes under wording (first reading each):")
    for s in POPULATION[REPORT]:
        rs = readings.get(_key("wording", REPORT, s), [])
        if rs:
            print(f"  {_branch(rs[0]['meaning']):46s} «{s}»")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", choices=ARMS)
    parser.add_argument("--budget", type=float, default=480.0,
                        help="seconds after which no new batch is started")
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()

    from dialectical_framework.dialectical_reasoning import DialecticalReasoning
    from dialectical_framework.settings import Settings

    container = DialecticalReasoning.setup(Settings.from_env())
    _check_population()
    if args.report:
        _report()
        return
    if not args.arm:
        parser.error("--arm or --report")
    print(f"model {container.settings().ai_model}", flush=True)
    if args.arm == "wording":
        with _WordingPatch():
            asyncio.run(_run_arm(args.arm, args.budget))
    else:
        asyncio.run(_run_arm(args.arm, args.budget))


if __name__ == "__main__":
    main()
