"""
Hash citations never reach the person.

The Advisor's understanding renders every node as `T1+ [[abc1234]]` because the
model needs an address to name that exact node in a tool call, and
`_HOW_YOU_SPEAK` tells it the address is never a word for the thing. That rule
is prompt-enforced, and prompt enforcement scales with compliance, not with
intelligence: on the strong tier no archived reply cites a hash; on the weak
tier the pinned Advisor cited five in one round (`nexus-pinned`, 2026-09-21),
each one `[[69961e3]] Re+ is "..."` in the middle of counsel. A hash is the
one leak shape that is NEVER legitimate in person-facing text — unlike a bare
`T+`, which cannot be removed without breaking the sentence around it, and
unlike "the framework found", which is a sentence the model has to not write —
so it is the one shape the framework can strip deterministically, on both entry
points, without touching what the model said.

Two functions with ONE contract: `strip_hash_citations(text)` over a whole
reply equals `HashCitationFilter` fed the same text in any chunking and
flushed. That equality is what lets `ResponseComplete.streamed` stay true —
the `message` a host receives must be byte-for-byte the deltas it rendered,
and both sides pass through the same rule. The filter holds back the least it
can: a trailing space, `[`, or an open `[[…` that might still become a
citation, and releases it the moment it cannot be one.

History is NOT filtered. The model's own reply, hashes and all, stays in the
conversation it can act on; only what the person sees is cleaned.
"""

from __future__ import annotations

import re

#: A rendered node address, with the space that usually precedes it, so
#: `the price [[abc1234]] you` becomes `the price you` and not `the price  you`.
#: Hashes are sha256 hexdigests rendered whole (64) or short (7); anything from
#: 6 up is accepted so a truncated render is still recognised, and a bracketed
#: word (`[[note]]`) is left alone because it is not an address.
HASH_CITATION = re.compile(r" ?\[\[[0-9a-f]{6,64}\]\]")

_HEX = frozenset("0123456789abcdef")


def strip_hash_citations(text: str) -> str:
    """The reply with every `[[hash]]` address removed."""
    return HASH_CITATION.sub("", text)


class HashCitationFilter:
    """Streaming form of `strip_hash_citations`: feed chunks, get clean text.

    Equal to the regex over the concatenation whatever the chunk boundaries —
    `tests/test_reply_hygiene.py` drives every split of a corpus through both
    and compares. Holding back is bounded: at most one space, two brackets and
    64 hex characters wait for the next chunk.
    """

    def __init__(self) -> None:
        self._pending = ""

    def feed(self, chunk: str) -> str:
        self._pending += chunk
        out: list[str] = []
        while self._pending:
            start = self._pending.find("[[")
            if start == -1:
                # No open citation. Release everything except what could still
                # become one: a trailing "[" (half of "[["), or a trailing space
                # that would be swallowed if "[[" follows.
                keep = 0
                if self._pending.endswith(" ["):
                    keep = 2
                elif self._pending.endswith("[") or self._pending.endswith(" "):
                    keep = 1
                cut = len(self._pending) - keep
                out.append(self._pending[:cut])
                self._pending = self._pending[cut:]
                break
            # Text before the "[[", minus the one space the regex would take.
            head_end = start - 1 if start > 0 and self._pending[start - 1] == " " else start
            out.append(self._pending[:head_end])
            self._pending = self._pending[head_end:]
            citation_at = start - head_end  # index of "[[" inside pending
            body_start = citation_at + 2
            # The maximal hex run after "[[", and what follows it.
            end = body_start
            while end < len(self._pending) and self._pending[end] in _HEX:
                end += 1
            body_len = end - body_start
            after = self._pending[end:]
            if body_len > 64:
                verdict = "no"
            elif after == "" or after == "]":
                verdict = "wait"  # still all hex, or one "]" short of closing
            elif after.startswith("]]"):
                verdict = "yes" if body_len >= 6 else "short"
            else:
                verdict = "no"
            if verdict == "wait":
                break
            if verdict == "yes":
                # A citation: drop it, together with the space held in front.
                self._pending = self._pending[end + 2 :]
                continue
            if verdict == "short":
                release = end + 2
            else:
                # Cannot be an address: release ONE bracket and rescan, because
                # the second bracket may open a real address (`[[[abc1234]]]`
                # strips to `[]`, exactly as the regex does).
                release = citation_at + 1
            out.append(self._pending[:release])
            self._pending = self._pending[release:]
        return "".join(out)

    def flush(self) -> str:
        """Whatever is still held back, released as-is at the end of the reply."""
        rest, self._pending = self._pending, ""
        return rest
