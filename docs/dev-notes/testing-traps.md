# Testing traps

<!-- Moved verbatim out of CLAUDE.md on 2026-09-18. This is lab-notebook material:
the reasoning behind a change, the measurements that justified it, and the traps hit
on the way. Figures are as-of the run that produced them; re-derive with the named
probe before quoting one. The rules distilled from these notes live in CLAUDE.md. -->

## The suite takes ~40 minutes

**The full suite takes ~40 minutes — background it.** Measured 2026-09-17 on this box: `2608 passed, 41 skipped in 2369.95s (0:39:29)`, mocked (no `--real-llm`). Two consequences. **Run ONE graph-touching pytest at a time**: concurrent runs against the single Memgraph deadlock, and a killed run leaves it wedged so the next one needs `docker compose -f docker-compose.test.yml restart`. And a backgrounded pytest redirected to a file leaves that file EMPTY until it exits, so poll `pgrep -f "bin/pytest"` rather than tailing the log and concluding it hung. Scope to a path or `-k` while iterating; the 40 minutes is for the pre-commit run.

## Bytecode trap when mutation-testing

**Bytecode trap when mutation-testing progress.** Reverting a one-character mutation (`expect_progress(1)`→`(2)`) by restoring a backup file can leave the SAME size and an mtime no newer than the `.pyc` compiled from the mutant, so Python reuses stale bytecode and the test keeps failing against source that is already correct. `touch` the file (or drop `__pycache__`) after any restore-by-copy.

## The event buses are globals wired once

**The two event buses are CLASS/MODULE globals wired once by a SESSION-scoped fixture, so `set_event_bus(None)` in a `finally` is not a teardown — it is a leak for the rest of the run.** `di_container` calls `ExecutionReport.set_event_bus(container.event_bus())` and `progress.set_event_bus(...)` exactly once, so a test that swaps either and then sets `None` unwires the container's own bus for every module that sorts after it. **The symptom is silent and does not look like a wiring bug**: reports still buffer, progress calls stay no-ops the way they are designed to, every tool returns the right answer, and only a test that SUBSCRIBES to a bus sees that it received nothing. That is exactly how `tests/test_graph.py::test_perspective_combination_delivers_effects_while_it_runs` failed at `0 > 0` inside the full suite while passing alone — `test_event_bus.py::TestExecutionReportEventIntegration` ended two of its three tests on `set_event_bus(None)`. Save and restore the PREVIOUS value (`previous = ExecutionReport._event_bus` / `progress_module.set_event_bus(previous)` — the pattern every progress-test module already uses); that class now does it in an autouse fixture rather than per test. And **a test that subscribes should assert its own wiring first**, because "nothing arrived" is indistinguishable from the defect such a test exists to catch: the one above checks `ExecutionReport._event_bus is bus` before it starts, so a future leak fails with the cause instead of with the symptom.

## A patch installed above its own `try` leaks into the whole process

`tests/e2e/probe_plus_takeup.py::_arm` monkeypatched
`AspectGeneration._tetrad_prompt`, then built the baseline system prompt, and
only then opened the `try` whose `finally` restored both. The build step
asserts on the production prompt, so when the production prompt changed
(2026-10-01, the worked plus example removed) that assertion fired with the
wrapper already installed and no `finally` to take it off. Every later render
in the PROCESS then went through a baseline arm that raised.

Cost: **23 failures in four other files** — `test_analyst_polarity_editing`,
`test_anchor_fanout_expansion`, `test_perspective_validation_wiring`,
`test_tool_progress_scopes` — none of which touch the probe, all of which pass
in isolation. The probe's guards are re-collected into the default suite
(`TestPlusTakeUpProbeGuardsRunInTheDefaultSuite`), so a probe-local leak became
a suite-wide one, and the failure list pointed at the graph and the progress
channel rather than at a prompt-arm reconstruction.

Rules:
- **Install the patch inside the `try`.** Everything that can raise goes after
  it, setup included. "Setup cannot fail" is the assumption that fails.
- A guard that a context manager restores after a raise in its BODY does not
  cover a raise in its SETUP — write both (`_arm`'s two tests), and
  mutation-test by moving the install back above the `try`.
- When a suite-wide failure list spans unrelated files but each file passes
  alone, suspect a leaked patch from whatever ran FIRST (`tests/e2e/` sorts
  before `tests/test_*`), not the change under test.
