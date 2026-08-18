"""Do the POOR_FIT-exemption pins actually fire? Fourteen mutations, run and report.

    poetry run python tests/bench/mutate23a.py

A pin that cannot fail is documentation. The exemption added 2026-08-18 changes
which cells `drop_invalid` deletes, so every branch of it gets a mutation:

  1. exemption deleted            -> the bug restored
  2. keyed on PREMATURE instead   -> the wrong control exempted
  3. keyed on "any known kind"    -> DECISION cells silently revalidated
  4. writer side removed          -> the fix inert on every new run
  5. field default flipped        -> archived records silently revalidated

The smoke run also moved the archive's own claim from "no control has ever RUN"
to "no control has been READ", stated at four sites across two files. Nine more
mutations check that it cannot drift apart (6-14): one per site, plus three that
sneak a CELL COUNT back next to the claim.

THREE WAYS THIS SCRIPT OR ITS PINS HAVE LIED, all fixed here:

  * A pytest selector matching NOTHING exits nonzero, which reads as "the
    mutation was caught". Every selector is asserted to match >=1 test first.
  * A pin that asserts a phrase ONCE is satisfied by any of its copies. The
    "reading guide 6 reverts" mutation survived the first draft for exactly that
    reason. Keep the per-site mutations — they are the only thing that
    distinguishes "stated at three sites" from "grepped once".
  * A pin that COUNTS occurrences breaks on documentation edits (adding a Files
    row moved the count 3 -> 4). Check each site's own wording instead.

And the claim itself must quote no cell count: the first draft said "4 cells" at
three sites, and re-smoking the fix made all three stale within the hour. Same
brittleness that broke the "392 saved runs" pin. Mutations 7, 12 and 14 are the
guard.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / "tests" / "bench" / "models.py"
DRIVER = ROOT / "tests" / "bench" / "driver.py"
REPORT = ROOT / "tests" / "bench" / "report.py"
README = ROOT / "tests" / "bench" / "README.md"

SURFACES = "test_all_three_surfaces_say_read_not_run"

MUTATIONS: tuple[tuple[str, Path, str, str, str], ...] = (
    (
        "exemption deleted (the bug restored)",
        MODELS,
        "        if self.scenario_kind is ScenarioKind.POOR_FIT:\n"
        "            # Not \"exempt from scrutiny\": an empty graph here is the PASS\n"
        "            # condition, and `poor_fit`'s three NI dimensions score the answer on\n"
        "            # its own terms. `wove_no_pathway` still reports what was built.\n"
        "            return False\n",
        "",
        "test_on_a_poor_fit_control_an_empty_graph_is_not_a_collapse",
    ),
    (
        "keyed on PREMATURE instead of POOR_FIT",
        MODELS,
        "if self.scenario_kind is ScenarioKind.POOR_FIT:",
        "if self.scenario_kind is ScenarioKind.PREMATURE:",
        "test_on_a_poor_fit_control_an_empty_graph_is_not_a_collapse or "
        "test_a_premature_control_with_an_empty_graph_still_collapses",
    ),
    (
        "keyed on 'any known kind'",
        MODELS,
        "if self.scenario_kind is ScenarioKind.POOR_FIT:",
        "if self.scenario_kind is not None:",
        "test_a_non_control_scenario_with_an_empty_graph_still_collapses",
    ),
    (
        "writer side removed (fix inert)",
        DRIVER,
        "            scenario_kind=scenario.kind,\n",
        "",
        "test_the_driver_records_the_scenarios_kind_on_the_cell",
    ),
    (
        "field default flipped to POOR_FIT",
        MODELS,
        "    scenario_kind: Optional[ScenarioKind] = None",
        "    scenario_kind: Optional[ScenarioKind] = ScenarioKind.POOR_FIT",
        "test_an_unknown_scenario_kind_takes_the_strict_reading",
    ),
    # -- the "READ, not RUN" claim, one mutation per site ------------------
    (
        "printed report reverts to 'EVER RUN'",
        REPORT,
        "NO CONTROL HAS BEEN READ",
        "NO CONTROL HAS EVER RUN",
        SURFACES,
    ),
    (
        "printed report re-quotes a count",
        REPORT,
        "premature_relocation have cells only under smoke* stems, which",
        "premature_relocation have only the 4 cells of smoke-r23-wiring, which",
        SURFACES,
    ),
    (
        "README drops the census annotation",
        README,
        "> **Annotation, added hours later — the census above is left as written.**",
        "> **Annotation.**",
        SURFACES,
    ),
    (
        "README's pre-registered census silently EDITED instead of annotated",
        README,
        "**zero cells in\nthe entire archive**",
        "**4 smoke cells in\nthe entire archive**",
        SURFACES,
    ),
    (
        "reading guide item 6 reverts",
        README,
        "has been READ. This line stood",
        "has been read. This line stood",
        SURFACES,
    ),
    (
        "correction-block update reverts",
        README,
        "by the `smoke*` rule in `_stems()`. **No control has\n> been READ.**",
        "by the `smoke*` rule in `_stems()`. **No control counts.**",
        SURFACES,
    ),
    (
        "a stale cell count creeps back into the claim",
        README,
        "> **Updated later the same day:** the controls now have cells",
        "> **Updated later the same day:** the controls now have 4 cells",
        SURFACES,
    ),
    (
        "reading guide 6 re-quotes a count",
        README,
        "`premature_relocation` have cells only under `smoke*` stems",
        "`premature_relocation` have only the 4 cells under `smoke*` stems",
        SURFACES,
    ),
    (
        "census annotation's own claim reverts",
        README,
        "claim — that **no control has been READ** — still holds",
        "claim — that no control counts — still holds",
        SURFACES,
    ),
)


def _selector_matches(selector: str) -> int:
    """How many tests `selector` picks. Zero means a false CAUGHT is coming."""
    proc = subprocess.run(
        ["poetry", "run", "pytest", "tests/bench/test_bench.py", "-k", selector,
         "--collect-only", "-q"],
        cwd=ROOT, capture_output=True, text=True,
    )
    match = re.search(r"(\d+)/\d+ tests collected", proc.stdout) or re.search(
        r"^(\d+) tests? collected", proc.stdout, re.M
    )
    return int(match.group(1)) if match else 0


def main() -> int:
    survivors: list[str] = []
    for label, path, old, new, selector in MUTATIONS:
        found = _selector_matches(selector)
        if not found:
            print(f"  ?? {label}: SELECTOR MATCHES NOTHING — cannot trust the result")
            survivors.append(label)
            continue

        original = path.read_text()
        if old not in original:
            print(f"  ?? {label}: target text NOT FOUND in {path.name}")
            survivors.append(label)
            continue
        path.write_text(original.replace(old, new, 1))
        try:
            proc = subprocess.run(
                ["poetry", "run", "pytest", "tests/bench/test_bench.py", "-k",
                 selector, "-q", "--no-header", "-p", "no:randomly"],
                cwd=ROOT, capture_output=True, text=True,
            )
        finally:
            path.write_text(original)
        caught = proc.returncode != 0
        print(f"  {'OK  CAUGHT ' if caught else '!!  SURVIVED'} {label}  ({found} test(s))")
        if not caught:
            survivors.append(label)

    print()
    if survivors:
        print(f"{len(survivors)} unpinned: " + "; ".join(survivors))
        return 1
    print(f"all {len(MUTATIONS)} mutations caught")
    return 0


if __name__ == "__main__":
    sys.exit(main())
