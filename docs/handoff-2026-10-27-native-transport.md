# Handoff from alsotrue, 2026-10-27: the native transport stalls before headers, and splits a structured reply

From the first app (`alsotrue`, the sibling repo), the day it moved its local run from
`bedrock/*` to `anthropic/*` on framework 2.1.2. Two findings from one afternoon, four fresh
draws of one 1,070-character Lithuanian post plus two English smoke cards. Not a measurement;
a reproduction with a count. The app has made its own side answer properly (last section);
the two asks below are the framework's.

Sonnet 5.5 native, `Consultant.exploration_view` with `attempts=3`, the app's text and
closing calls after it; the app's read timeout as configured locally (the framework default,
120 s), `DIALEXITY_MAX_CONCURRENT_LLM_CALLS` as configured.

## 1. Three of four draws died on "stream did not open within 5s"

`utils/bedrock_provider.py:470` gives a streamed call `headers_budget =
min(_STREAM_HEADERS_TIMEOUT_S, read_timeout_s)` = **5.0 s** to return headers, a module
constant (`:425`), not a setting. `use_brain` re-asks once on the stall. On the native
transport, with `_SDK_MAX_RETRIES = 0` (`:118`, so this is real time-to-first-byte, not the
SDK's own backoff), the sequence on three of four fresh sessions was: stall at 5 s, re-ask
after 2 s, stall at 5 s, raise `StreamReadTimeout`. Six of eight attempts across those three
requests never saw headers in 5 s. A second run of eight the same hour, after the app mapped the error: three more
stalled the same way, so **six of twelve fresh sessions** were lost to it; the five that
landed took 29–40 s.

| request | where it died | calls made | provider s | spent |
|---|---|---|---|---|
| 1 | inside the view turn | 14 | 50.4 | $0.084 |
| 2 | the gate, first call (`StanceCaptureDto`) | 1 | 2.2 | $0.002 |
| 3 | the gate, first call | 1 | 2.2 | $0.002 |
| 4 | landed, 42.8 s wall | 19 | 79.3 | $0.111 |

The same warning appears on Bedrock in the app's 2026-10-20 probe log (Opus 5.5 and Sonnet
5.5 both "stalled before headers (5.0s)"), and there the re-ask recovered every time. The
prompts here are large and cached (78k cache-read tokens a card): a cache read should be fast
to first byte, but 5 s is evidently under the native API's tail on this account, and a budget
that is right for Bedrock's inference profiles may not be right for `api.anthropic.com`.

**Ask.** Make the header budget a setting (`llm_stream_headers_timeout_s`, or derive it from
`llm_connect_timeout_s`), or at least a per-transport default, so a host can widen it where
the measured tail says so. Two re-asks instead of one would also have landed all three.
Whatever is chosen, the host needs to see it: the app now maps the framework's
`httpx.ReadTimeout` subclass to the same 503 as its card deadline, so a person gets "try
again" rather than a 500.

## 2. A structured reply split inside a field

On the one Lithuanian card that landed earlier the same hour (the app's own draw, not the
four above), the text call's `paragraph` ended mid-word after four whole sentences and a cut
fifth, and the `parallel` (story) field began with the paragraph's missing tail followed by
an English "There's". The app's story check caught the story as "a truncated, incoherent
fragment" and rewrote it; nothing read the paragraph, so the fragment reached the card.

This is the signature your 2026-10-26 note describes for the native transport (a json-mode
call "asked for in prose", `91fd7d2`), reproduced after `dddf139` moved the compat layer to
the provider-neutral seam. One occurrence in two Lithuanian cards; both English cards were
whole. Whether the split is the parser's (a field boundary found at the wrong index) or the
model's (writing past the ceiling into the next key) is not visible from the app; the raw
response is.

**Ask.** Whatever the native structured path does with a reply whose field values run into
each other, surface it: a validation failure the host can re-ask on, or a log line with the
DTO and the raw tail, rather than a silently truncated field. The app now trims a cut
paragraph to its last whole sentence and re-asks once when nothing whole remains; it would
rather know.

## What the app changed on its side

- `httpx.ReadTimeout` (which `StreamReadTimeout` subclasses) is caught at the gate and the
  draw and answered as the existing 503 "That took too long", which the client retries. The
  two API tests name the two paths.
- The paragraph is checked for a whole last sentence (`synthetic_wisdom.whole_paragraph`),
  trimmed when cut, re-asked once when nothing is left.
- Prices are keyed on the model, not the transport, so a native card is billed.

## Reproducing

From `alsotrue/backend` with the local stack up and a native model configured: open four
sessions with the same long post through `POST /api/v1/sessions` and read `.dev/api.log` for
"Stream stalled on … before headers (5.0s)" and the `Unhandled exception` line that followed
until the fix. The framework's own `tests/e2e/probe_view_turn_ask.py` on the native transport
is the right instrument for the stall rate once the budget is a setting.
