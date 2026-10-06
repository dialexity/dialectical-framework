# Hand-off: three token levers measured from the alsotrue app (2026-10-06)

For whoever works on the framework next. Everything below was measured with the
framework's own call census (`utils/call_census.py`) around the alsotrue app's
real entry points, on Sonnet 5 via Bedrock, and is reproducible with the app's
retry-routing eval (`alsotrue-app/backend/evals/retry_routing/`, 40 cases,
`--reps 2`; paired deltas against `v1`). Cost figures are at Anthropic list
prices as a proxy for Bedrock (Sonnet 5 $2/$10 per MTok, cache reads 0.1x,
cache writes 1.25x).

## What one card costs today (the view turn's host, one first card, 11 calls)

| call | n | prefill read (cached) | uncached | output |
|---|---|---|---|---|
| gate (`StanceCaptureDto`) | 1 | 0 | ~250 | ~90 |
| view turn, best-of-3 (`ViewSketchDto`) | 3 | 11,874 each | ~1,520 each | ~370 each |
| coherence judge (`CoherenceEvaluationDto`, 2 control statements x 3 candidates) | 6 | 1,165 each | ~680 each | **~550 each** |
| pill (`TransformationPillDto`, app-side) | 1 | 1,810 | ~400 | ~620 |

Per card: ~45k prefill read from cache ($0.009), ~9k uncached ($0.018),
**~5.1k output ($0.051)** — about $0.10. Prompt caching is working: 69–83% of
all prefill in the eval was served from cache (the ~11.9k-token Consultant
system prompt, split onto the stable head by `split_system_for_cache`). The
money is in output tokens, and two-thirds of the output is the judge.

## 1. One call for the coherence judge — the big one (~-30% per card)

**Now.** `concerns/tetrad_candidates.py::select_sketch` judges each candidate
with `judge_sketch`, which makes one `CoherenceEvaluationDto` call PER control
statement: 2 x 3 candidates = 6 calls, each ~550 output tokens (reasoning),
~7–8 s, run in parallel. 3.3k of a card's 5.1k output tokens; ~$0.033 of
$0.10.

**Change.** One structured call per draw that reads all three candidates'
first tensions and returns three verdicts (the two control-statement scores
and a short reason each). Expected: ~1k output instead of 3.3k, one
round-trip instead of six. Keep `SketchVerdict` and `ranking()` as the
interface so nothing downstream moves; the parallel judging of independent
candidates becomes one call with a list DTO.

**Watch for.** Position bias (the candidate listed first winning), and the
judge comparing candidates to each other instead of scoring each against the
control statements — the docstring's rule stands: the judge must not see the
thesis/antithesis, only the four aspects, and selection must stay "among
independent draws", never regeneration from the verdict. Judge stability was
measured at 92% on re-judging the same text (`antithesis-selection.md`,
"Best-of-N"); re-measure it for the joint call with the same probe, and run
the app's eval at `--reps 2` as `v<N>` for the paired card-quality number.
If the joint verdict's stability drops below ~85%, fall back to one call per
candidate (3 calls, both statements in one DTO): still half the output.

## 2. Cold starts: the three parallel draws each WRITE the 11.9k head

**Now.** Best-of-3 runs the three `ViewSketchDto` calls with `asyncio.gather`.
On a warm cache all three read the head (3 x 11,874 read). When the cache is
cold — any gap over the 5-minute TTL, which for a single early user is every
session — none can read what the others are still writing, so all three
write: 3 x 11.9k x 1.25 x $2/MTok = **$0.089** of writes where a warm card pays
$0.007 of reads. The seed run showed it exactly: the first card wrote 45,704
tokens, every later one read 45,704.

**Two changes, independent, in `utils/bedrock_provider.py` and the view turn:**

- **Stagger the gather.** Fire one draw, wait for its first streamed token (not
  the full response — the entry becomes readable once the first response
  begins streaming), then fire the other two; they read what it wrote. Cost on
  a cold start: 1 write + 2 reads instead of 3 writes (saves ~$0.06); latency
  cost: one TTFT (~1–2 s) on cold starts only. On a warm cache nothing
  changes. The sketch turns are non-streaming today (`sketch_turn.submit`);
  the simplest honest form is "await the first draw entirely, then the two",
  which costs one full draw's latency (~6 s) on cold starts — measure which.
- **1-hour TTL on the system head's breakpoint** (`split_system_for_cache`
  writes `cache_control={"type": "ephemeral"}`; add `"ttl": "1h"` there). The
  write costs 2x instead of 1.25x but survives an hour of idle; break-even is
  three reads. Entries with the longer TTL must come BEFORE shorter ones in
  the request, which holds (the head is the first breakpoint). Bedrock
  supports the 1h TTL on Claude 4.x+; verify once with
  `usage.cache_creation.ephemeral_1h_input_tokens` on the response.

## 3. The view-sketch request's static part into the cached head (small)

**Now.** `concerns/view_sketch.py::view_sketch_prompt(focus, component_length)`
is sent as the USER message of every sketch turn: the definitions and the
procedure (static, ~1.2k tokens) plus the focus (per call). It sits after the
history, so it is never cached: 3 x ~1.2k = ~3.6k uncached per card
(~$0.007).

**Change.** Append the static part to the Consultant's system prompt for the
sketch turn (the `sketch_turn` facilitator is a copy of the head's history;
give it `set_system_prompt(head_system + "\n\n" + static_request)` and send
only `What to show: <focus>` as the user message). The head's breakpoint
then covers it. Mind the test that pins the history record
(`test_view_sketch.py`: the long request must NOT be kept in the history —
unchanged by this, since the record is written by `history_ask`).

Worth doing only alongside 1 or 2; on its own it is $0.007 a card.

## Not levers (checked)

- The pill, the gate and the app's shift classifier are 1–2k-token prompts:
  the gate's and pill's system prompts cache (1,282 / 1,810 read); the shift
  classifier's ~1.4k is uncached and costs $0.003 a retry. Nothing to gain.
- Output tokens of the draws themselves (~370 each) are the tetrad; not
  compressible without changing the method.

## How to verify a change end to end

```
cd alsotrue-app/backend
POSTGRES_DB=alsotrue_eval PYTHONPATH=$PWD uv run python evals/retry_routing/run.py --variant v<N> --reps 2 --approve-harness
node <claude-api skill>/shared/evals/report/build-report-lite.mjs ../.claude/hillclimb/retry_routing/
```

The report pairs `v<N>` against the baseline per case; `cost_usd` (proxy),
`latency_s`, `in_tokens`, `out_tokens` are per row, and
`usage.cache_read_input_tokens` / `cache_creation_input_tokens` say whether
the cache behaved. Write `v<N>/change.md` and `change.patch` so the report
shows what changed.
