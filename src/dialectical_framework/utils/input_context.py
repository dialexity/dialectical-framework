"""
Utility for building input context from digests for downstream LLM concerns.

Follows the same <Input id="..."> tagging pattern as CompositeInputResolver.resolve_all(),
but prefers digest over full content resolution.

**This is bounded, and the bound is load-bearing.** It used to render every
Input in scope at full length, and the fallback for an Input whose digest had
not been written is its ENTIRE content. Three pasted ~400 KB files therefore
rendered 1.22 MB — about 300k tokens — measured in
`tests/probe_input_text_cost.py`; and five of the seven consumers of this
string never truncate what they are handed (`aspect_generation`,
`perspective_validation`, `control_statements_check`,
`antithesis_classification`, `tetrad_grounding` — only `statement_headline`
and `statement_classification` cut, at 1500/2000). So an undigested large
source was a context-limit failure or a ruinous bill, once per polarity, not
a slowdown.

Two things follow, and both are deliberate:

**The budget is shared out, not applied per Input.** A per-Input cap still
grows without limit in the number of Inputs, and the number of Inputs is
whatever the person pasted. `_allocate` water-fills instead: every source is
promised an equal share, sources that need less than their share hand the
remainder back, and the ones that want more split what is left. A scope of
one small digest and one huge document does not punish the small one, and
twenty digests all fit.

**A cap announces itself.** Same argument as `statement_headline` and
`synthesis_generation`: a document cut silently reads as one that simply
ended there, so the model treats a fragment as the whole source and reasons
confidently from a beginning. Each cut source carries `shown`/`of` and a
`...` marker; a source squeezed to nothing is still NAMED, because "there is
a third source and you were shown none of it" is a different fact from
"there are two sources".

The `<Input id="...">` tag is for attribution, NOT an off-ramp: this string
goes into concern prompts, whose inner model has no tools at all. Do not
write "use read_input to see the rest" here — that is the dead off-ramp
`ingest`'s digest note avoids for the same reason.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.input import Input
    from dialectical_framework.protocols.input_resolver import InputResolver

#: Total characters of source material one rendered context may carry.
#: ~6k tokens: the same order as the largest prompt the tree already ships
#: (the ~15.6k-token Advisor engine), so the worst concern call stays
#: comparable to something known to work, while ~8-20 typical digests
#: (1-3k chars each) still render uncut. A module constant rather than a
#: setting because no deployment has a reason to pick a different number —
#: promote it if one turns up.
INPUT_CONTEXT_BUDGET = 24_000

#: Below this an allocation is not worth spending: a couple of sentences of a
#: 400 KB document is not grounding, it is a misleading fragment. Such a
#: source is named with nothing shown instead.
_MIN_USEFUL_ALLOCATION = 200


def _allocate(lengths: list[int], budget: int) -> list[int]:
    """Share `budget` across `lengths` by water-filling.

    Every source is promised `budget // n`. Anything shorter than its share
    takes only what it needs and releases the rest, which is re-shared among
    the sources still asking for more — repeatedly, since releasing may lift
    the share above another source's length. When every remaining source
    wants more than its share, they split the remainder evenly.

    Returns one allocation per input, in the same order. An allocation may be
    0 (see `_MIN_USEFUL_ALLOCATION`).
    """
    allocations = [0] * len(lengths)
    remaining = budget
    pending = list(range(len(lengths)))

    while pending:
        share = remaining // len(pending)
        if share < _MIN_USEFUL_ALLOCATION:
            # Nothing left worth handing out; whoever is still pending shows
            # nothing rather than a sentence fragment.
            break

        satisfied = [i for i in pending if lengths[i] <= share]
        if not satisfied:
            # Everyone wants more than their share — split evenly and stop.
            for i in pending:
                allocations[i] = share
            break

        for i in satisfied:
            allocations[i] = lengths[i]
            remaining -= lengths[i]
        pending = [i for i in pending if lengths[i] > share]

    return allocations


async def input_context(
    inputs: list[Input],
    input_resolver: InputResolver,
    budget: int = INPUT_CONTEXT_BUDGET,
) -> str:
    """
    Get labeled digests from inputs for injection into LLM prompts.

    Each input's digest (or fallback full content) is wrapped in <Input id="...">
    tags so the LLM knows which source it came from, and the whole rendering is
    held to `budget` characters — see the module docstring for why the bound and
    its signalling are not optional.

    Args:
        inputs: List of Input nodes to get digests from
        input_resolver: Resolver for fallback when digest is not yet available
        budget: Total characters of source material to render. The default is
            the right answer; the parameter exists so a test can pick a small
            number instead of building a megabyte.

    Returns:
        Combined text with each input wrapped in <Input> tags. A cut source
        carries `shown`/`of` and a trailing `...`; a source that got no
        allocation is named with `shown="0"` and no body. Empty string if no
        inputs or all inputs have no content.
    """
    if not inputs:
        return ""

    # Resolve first: allocation needs the real lengths, and the digest-vs-
    # content decision is what determines them.
    resolved: list[tuple[Input, str]] = []
    for input_node in inputs:
        if input_node.digest:
            text = input_node.digest
        else:
            text = await input_resolver.resolve(input_node)

        if not text:
            continue

        resolved.append((input_node, text))

    if not resolved:
        return ""

    allocations = _allocate([len(text) for _, text in resolved], budget)

    parts = []
    for (input_node, text), allowance in zip(resolved, allocations):
        if allowance >= len(text):
            parts.append(f'<Input id="{input_node.hash}">\n{text}\n</Input>')
        elif allowance == 0:
            parts.append(
                f'<Input id="{input_node.hash}" shown="0" of="{len(text)}" '
                f'truncated="true" />'
            )
        else:
            parts.append(
                f'<Input id="{input_node.hash}" shown="{allowance}" '
                f'of="{len(text)}" truncated="true">\n'
                f"{text[:allowance]}...\n</Input>"
            )

    return "\n\n".join(parts)
