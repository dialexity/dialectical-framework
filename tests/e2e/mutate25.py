"""Do the r25 pins actually fire? Twenty-seven mutations, run and report.

    poetry run python tests/e2e/mutate25.py

A pre-registration is only worth its cost if the costly clauses cannot be quietly
removed after the result. r25 is the round most exposed to being re-narrated —
fourth edit on one behaviour, in open contradiction of r24's own "Stop editing
this paragraph" — so the clauses that constrain a future session get mutated:

  1-2   the pre-commitment ("no fifth wording") deleted / stripped of its
        structural alternative, leaving a mood instead of a plan
  3-5   the overshoot check demoted: moved after the endpoint, its two-halves
        requirement dropped, or promoted to cancel the endpoint outright
  6-7   the endpoint moved with the prompt (the absolute bar, in prose and in code)
  8-10  the pooled null reverted at each of the three sites that state it
  11-13 code/prose divergence on the null, and a dissolution folded into resize
  14-15 the theory justification removed, or the discriminator put back on DEPTH
  16    r24's verdict loses its forward pointer (the log contradicts itself)
  17    the overshoot threshold raised past n, so the check can never fire

And then the RESULT, added after the run, where the pressure is different in kind. r25
came in at 6/12 — the one integer its own pre-registration states two incompatible
readings about — so every mutation below is a way a later session could read this round
as a win without editing a single number:

  19-20 the verdict rounded up: the absolute-bar miss deleted, or the significant
        contrast promoted to the whole finding
  21-22 the pre-registration's defective bands row quietly repaired, or its
        correction pointer detached from it
  23    a hand label flipped so the prose and the labels disagree
  24    the post-hoc split-cell shape promoted to a fourth label, which is the
        one edit that would let the round raise its own count
  25    the non-significant end of the bracket (3/12, p = 0.156) dropped
  26    "no fifth wording" dropped once the pre-commitment's band was missed
  27    "0 of 36" widened to a pre-fork stem without re-reading the claim

WHAT THIS SCRIPT INHERITS FROM `mutate23a.py`, INCLUDING ITS SCARS
=================================================================
  * A pytest selector matching NOTHING exits nonzero, which reads as CAUGHT.
    Every selector is asserted to match >=1 test before the mutation is applied.
  * A pin that asserts a phrase ONCE is satisfied by any of its copies, so the
    per-SITE mutations are kept rather than collapsed into one grep.
  * A target spanning a line break will not be found. `rounds.md` is hard-wrapped,
    so every target below is either short enough to sit on one line or carries the
    newline explicitly — and a NOT FOUND counts as UNPINNED, never as CAUGHT.

The inert-guard mutation (17) is the one this round most needed: a threshold above
the run size passes silently, which is how the `@pytest.mark.timeout` decorators
and the first leak scanner both looked green while doing nothing.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROUNDS = ROOT / "tests" / "e2e" / "rounds.md"
PROBE = ROOT / "tests" / "e2e" / "probe_price_arithmetic.py"

PREREG = "test_the_pre_commitment_that_a_null_ends_prose_attempts"
OVERSHOOT = "test_the_overshoot_check_is_read_before_the_endpoint"
ENDPOINT = "test_the_endpoint_is_unchanged_so_the_baselines_still_mean_something"
AGREE = "test_the_probe_agrees_with_the_pre_registered_baseline"
THEORY = "test_the_theory_finding_is_what_justifies_a_fourth_edit"
POINTER = "test_the_previous_rounds_verdict_carries_the_forward_pointer"
REACHABLE = "test_the_overshoot_threshold_is_reachable_and_not_a_hair_trigger"
BAR = "test_the_endpoint_bar_did_not_move_with_the_prompt"
PARTITION = "test_a_dissolution_counts_against_the_endpoint_not_for_it"
VERDICT = "test_the_verdict_is_resolved_against_the_fix"
CONTRADICTION = "test_the_pre_registrations_own_contradiction_is_reported_not_edited"
RECORDED = "test_the_probe_agrees_with_the_recorded_result"
SPLIT = "test_the_post_hoc_split_cells_do_not_change_the_endpoint"
BRACKET = "test_the_non_significant_end_of_the_bracket_stays_visible"
NOFIFTH = "test_no_fifth_wording_survives_even_though_the_pre_commitment_missed"
SCOPED = "test_the_claim_that_the_shape_is_new_is_scoped_to_the_fork"

MUTATIONS: tuple[tuple[str, Path, str, str, str], ...] = (
    # -- the pre-commitment: the only clause that binds a future session ----
    (
        "pre-commitment deleted (a fifth wording becomes reasonable again)",
        ROUNDS,
        "**PRE-COMMITMENT, recorded before the run and binding: if this nulls, no fifth wording\ngets written.**",
        "The fork may or may not land.",
        PREREG,
    ),
    (
        "pre-commitment kept but stripped of what happens INSTEAD",
        ROUNDS,
        "the next move is the structural one r24 already named — a `record_decision`-side\ncheck that an `accepted_cost` was actually priced.",
        "the next move is something else.",
        PREREG,
    ),
    # -- the overshoot check, which runs AGAINST the fix --------------------
    (
        "overshoot demoted to be read after the endpoint",
        ROUNDS,
        "**NEW invalidating check, and it is read BEFORE the endpoint**",
        "**A further note, to be read after the endpoint**",
        OVERSHOOT,
    ),
    (
        "the `dissolve` label loses its two-halves requirement",
        ROUNDS,
        "The label requires BOTH halves\n— tension declared gone AND the recommendation withdrawn —",
        "The label applies when the tension is declared gone,",
        OVERSHOOT,
    ),
    (
        "the r24 failure shape allowed to relabel itself as a pass",
        ROUNDS,
        "which is the r24 failure\nshape and must not be laundered by the new vocabulary",
        "which is a borderline case",
        OVERSHOOT,
    ),
    (
        "overshoot promoted to cancel the endpoint (an all-or-nothing read)",
        ROUNDS,
        "an\novershoot does **not** cancel a resize-modal result, it caps the claim",
        "an\novershoot cancels a resize-modal result outright",
        OVERSHOOT,
    ),
    # -- the endpoint, and the cheapest possible way to fake a win ----------
    (
        "the absolute bar drops out of the pre-registration",
        ROUNDS,
        "the absolute MODAL bar `LANDED_MIN_SHARE = 0.5` reported",
        "the absolute bar reported",
        ENDPOINT,
    ),
    (
        "the bar itself lowered in code so 1/12 would 'land'",
        PROBE,
        "LANDED_MIN_SHARE = 0.5",
        "LANDED_MIN_SHARE = 0.08",
        BAR,
    ),
    # Three sites state the pooled null. The first draft of the ENDPOINT pin
    # grepped "3/36" once and SURVIVED the heading mutation, because the table and
    # the bands line still carried the number. One mutation per site.
    (
        "pooled null reverts at site 1 (the heading that says which runs pool)",
        ROUNDS,
        "**The baseline is 36 cells and pools r24 in.**",
        "**The baseline is 24 cells.**",
        ENDPOINT,
    ),
    (
        "pooled null reverts at site 2 (the table's pooled row)",
        ROUNDS,
        "| **pooled pre-fork** | | **3** | **33** |",
        "| pooled | | 3 | 33 |",
        ENDPOINT,
    ),
    (
        "pooled null reverts at site 3 (the bands table's null, where p comes from)",
        ROUNDS,
        "null = pooled pre-fork 3/36 = 0.083",
        "null = 0.083",
        ENDPOINT,
    ),
    # -- code/prose divergence on the null ---------------------------------
    (
        "code drops r24 from the fork's null (prose says 3/36, code says 2/24)",
        PROBE,
        "PRE_FORK_STEMS = CLAUSE_PRESENT_STEMS + (POST_FIX_STEM,)",
        "PRE_FORK_STEMS = CLAUSE_PRESENT_STEMS",
        AGREE,
    ),
    (
        "the fork's null applied to r24 too (r24's archived p=0.7165 changes)",
        PROBE,
        "    return PRE_FORK_STEMS if stem == FORK_STEM else CLAUSE_PRESENT_STEMS",
        "    return PRE_FORK_STEMS",
        AGREE,
    ),
    (
        "a `dissolve` label folded into `resize` (the fork inflates its own estimate)",
        PROBE,
        '        out[label].append(rep)',
        '        out["resize" if label == "dissolve" else label].append(rep)',
        PARTITION,
    ),
    # -- the theory finding, which is the whole justification --------------
    (
        "the gloss finding removed (the round becomes mere persistence)",
        ROUNDS,
        '"the framework author\'s gloss, 2026-08 — not a paper claim"**',
        "a rule worth restating**",
        THEORY,
    ),
    (
        "the discriminator put back on DEPTH — the axis r24's cells folded along",
        ROUNDS,
        "The discriminator is deliberately **not depth**.",
        "The discriminator is how deep the correction went.",
        THEORY,
    ),
    # -- the log must not contradict itself silently -----------------------
    (
        "r24's verdict loses the forward pointer",
        ROUNDS,
        "> **Overturned the next day, and the overturning is itself the finding.**",
        "> **Note.**",
        POINTER,
    ),
    # -- the inert guard --------------------------------------------------
    (
        "overshoot threshold raised past n (the check can never fire)",
        PROBE,
        "DISSOLVE_OVERSHOOT_MIN = 3",
        "DISSOLVE_OVERSHOOT_MIN = 13",
        REACHABLE,
    ),
    # ===================================================================
    # THE RESULT. 6/12 is the value the pre-registration disagrees with
    # itself about, so each of these is a way to read it as a win.
    # ===================================================================
    (
        "the absolute-bar miss deleted, leaving only the significant contrast",
        ROUNDS,
        "**VERDICT: DID NOT LAND on the absolute bar; MOVED on the contrast (p = 0.0042).**",
        "**VERDICT: MOVED (p = 0.0042).**",
        VERDICT,
    ),
    (
        "the contrast promoted to the whole finding (the 6/12 count goes)",
        ROUNDS,
        "**VERDICT: DID NOT LAND on the absolute bar; MOVED on the contrast (p = 0.0042).**",
        "**VERDICT: the fork moved the behaviour, p = 0.0042 against the pooled null.**",
        VERDICT,
    ),
    (
        "the defective bands row quietly repaired (the round becomes a clean win)",
        ROUNDS,
        "| **6+** | p ≤ 0.004 | **moved under the strictest reading available** and resize is at least modal — the only band clearing both bars. |",
        "| **7+** | p ≤ 0.001 | **moved under the strictest reading available** — the only band clearing both bars. |",
        CONTRADICTION,
    ),
    (
        "the correction detached from the row it corrects",
        ROUNDS,
        "> **This last row is wrong, and the run landed on it.** Left standing because a pre-registration\n> is not edited after the fact.",
        "> Note: see the result below.",
        CONTRADICTION,
    ),
    (
        "a hand label flipped to 7 resizes (prose and labels diverge)",
        PROBE,
        '    5: ("zero", "What\'s still true, and smaller than what I was carrying',
        '    5: ("resize", "What\'s still true, and smaller than what I was carrying',
        RECORDED,
    ),
    (
        "the split-cell shape promoted to a fourth label (the round raises its own count)",
        PROBE,
        'LABEL_NAMES = ("resize", "dissolve", "zero")',
        'LABEL_NAMES = ("resize", "dissolve", "zero", "resize_but_recorded_as_none")',
        SPLIT,
    ),
    (
        "the non-significant end of the bracket dropped (only p=0.0042 survives)",
        ROUNDS,
        "**3 to 6 of 12**",
        "**6 of 12**",
        BRACKET,
    ),
    (
        "'no fifth wording' dropped because the pre-commitment's band was missed",
        ROUNDS,
        "**and no fifth wording\ngets written anyway, for a stronger reason than the one pre-registered.**",
        "so a further wording remains available.**",
        NOFIFTH,
    ),
    (
        "'0 of 36' widened to a pre-fork stem without re-reading the claim",
        PROBE,
        '    "r25-probe-fork": {\n        1: "body \'what I\'d still say costs something\'',
        '    "r24-probe-mechanism": {},\n    "r25-probe-fork": {\n        1: "body \'what I\'d still say costs something\'',
        SCOPED,
    ),
)


def _selector_matches(selector: str) -> int:
    """How many tests `selector` picks. Zero means a false CAUGHT is coming."""
    proc = subprocess.run(
        ["poetry", "run", "pytest", "tests/e2e/test_e2e.py", "-k", selector,
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
                ["poetry", "run", "pytest", "tests/e2e/test_e2e.py", "-k",
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
