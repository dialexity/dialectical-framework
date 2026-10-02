"""
anchor tool: Plant a specific tension the LLM already sees.

Two modes:
- thesis + antithesis: full precision, creates polarity and perspective directly
- thesis only: anchors the position, discovers what opposes it
"""

from __future__ import annotations

from typing import Annotated

from mirascope import llm
from pydantic import Field

from dialectical_framework.utils.progress import progress_key


def _progress_key(thesis: str, antithesis: str | None) -> str:
    """A stable, opaque id for ONE anchor call's progress stream.

    Content-derived rather than a counter so it is stable across a retry of the
    same call, and hashed rather than truncated text so a host that renders the
    key verbatim cannot put the person's own words in a progress label — the
    convention `key=wheel.short_hash` already established elsewhere.
    """
    return progress_key(thesis, antithesis)


@llm.tool
async def anchor(
    thesis: Annotated[
        str,
        Field(description="The thesis position — what the person holds or champions"),
    ],
    antithesis: Annotated[
        str | None,
        Field(
            description="The opposing force; omit to discover what opposes the thesis"
        ),
    ] = None,
    context: Annotated[
        str,
        Field(
            description=(
                "The person's own specifics behind this tension — numbers, "
                "dates, equity splits, named events, concrete instances they "
                "cited, in their terms. Stored as the tension's grounding: the "
                "tetrad itself keeps only a few words per position, so this is "
                "the only place their particulars survive. Facts they stated, "
                "not interpretation, advice, or notes about the person."
            )
        ),
    ] = "",
) -> str:
    """Plant a specific tension into the graph. With both thesis and antithesis: creates the opposition directly and generates the full tetrad. With thesis only: anchors the position and discovers what opposes it. Use when you can see the person's position clearly."""
    from dialectical_framework.utils.progress import progress_scope

    # Measured at ~40s during which the person is told nothing: `call_census` puts
    # this tool at parallelism ~1.15, and nothing writes a graph node until a
    # perspective commits, so there is a single stage — tetrad generation, ~10.2s
    # of the ~38s on its own — that a person waits through with no signal at all.
    #
    # Progress is worth adding REGARDLESS of how much latency is left to remove,
    # which is the honest framing: `parallelism 1.15` reports overlap ACHIEVED, not
    # overlap available (`utils/call_census.py`), so it cannot say the chain is out
    # of opportunities — the gather in `IntroducePolarity.resolve` was found after
    # that reading and is exactly the opportunity such a claim would have closed.
    #
    # Installed HERE, above every branch, because a scope reaches a gathered child
    # only if the child's task is created after the scope is installed
    # (`utils/progress.py`) — the skills below gather their provider work, and
    # opening the scope inside a skill would leave those children silent.
    # `total` is left at 0 and grown by whoever discovers the work.
    #
    # `key` distinguishes CONCURRENT anchors: `execute_tools()` gathers a tool
    # round and runs it concurrently, so two `anchor` calls in one round share a
    # sid and publish two interleaved streams with two `final` events. Without a
    # key a host cannot tell them apart and clears its indicator on the first one
    # while the second is still working.
    from dialectical_framework.utils.utterance import current_utterance

    with progress_scope("anchor", key=_progress_key(thesis, antithesis)):
        # The ONE reader of the turn's utterance: the tool, which hands it on
        # explicitly. `_anchor` never reads the ContextVar itself, because the
        # off-turn task inherits the scheduling turn's context and would
        # attribute a note or a closing's anchor to whatever was said last.
        return await _anchor(
            thesis=thesis,
            antithesis=antithesis,
            context=context,
            utterance=current_utterance(),
        )


async def _keep_utterance(utterance: str | None, report_artifacts: dict) -> list[str]:
    """The person's words, verbatim, as an Input — or nothing.

    Why an Input and not a field: it is the framework's node for material, it
    dedups on content (the same turn anchoring twice, or the same words said
    again, is ONE Input), `ensure_digest` skips the model for anything short,
    `read_input`/`read_digest` already read it back, and `inputs_for_statements`
    makes it the context the tension is developed against instead of every
    digest in the case. Before 2026-10-01 the original wording was stored
    nowhere: the Statement keeps a ≤7-word headline and `context` is the
    model's paraphrase.

    Fail-soft: a failed capture costs provenance, never the anchor.
    """
    text = (utterance or "").strip()
    if not text:
        return []
    try:
        from dialectical_framework.concerns.add_input import capture_input

        input_node = await capture_input(text)
        if input_node is None or not input_node.hash:
            return []
        report_artifacts["input_hash"] = input_node.hash
        return [input_node.hash]
    except Exception:
        import logging

        logging.getLogger(__name__).exception(
            "Could not keep the person's words as an Input (fail-soft)"
        )
        return []


async def _anchor(
    *,
    thesis: str,
    antithesis: str | None,
    context: str,
    utterance: str | None = None,
) -> str:
    """The tool's body, so the progress scope wraps it without re-indenting it.

    Split out rather than nested purely to keep the diff on the reasoning path
    empty: every line below is unchanged from when it was inline.

    `utterance` is the person's turn, verbatim, when a turn is what this is
    running on: kept as an Input and linked to the poles as their source. None
    where there is no such turn — a closing's own anchor on an empty graph — and
    the note's own turn for a note planted later.
    """
    from dialectical_framework.agents.analyst.skills.expand_polarities import \
        ExpandPolarity
    from dialectical_framework.agents.analyst.skills.introduce_polarity import \
        IntroducePolarity

    source_artifacts: dict = {}
    input_hashes = await _keep_utterance(utterance, source_artifacts)

    if antithesis:
        introduce = IntroducePolarity(
            thesis=thesis,
            antithesis=antithesis,
            text=context,
            input_hashes=input_hashes,
        )
        result = await introduce.resolve()

        if not result.primary_polarity_hash:
            return str(introduce.report)

        # `context` grounds the tetrad, not just its classification: the poles
        # are capped near seven words and deduped, so without this the case
        # particulars are used once for classification and then lost.
        expand = ExpandPolarity(
            polarity_hash=result.primary_polarity_hash,
            grounding_context=context,
        )
        perspectives = await expand.resolve()

        combined_report = introduce.report.merge(expand.report)
        combined_report.artifacts["perspective_hashes"] = [
            pp.hash for pp in perspectives if pp.hash
        ]
        combined_report.artifacts.update(source_artifacts)
        return str(combined_report)

    # Thesis only: the ONE-SHOT build (2026-10-01). One thinking call over the
    # person's words writes the antithesis and the four aspects around the
    # given thesis; `IntroducePolarity` and `ExpandPolarity(given_tetrad=)`
    # then classify, score, dedup, ground, validate and persist it as a normal
    # tetrad. It replaced the staged build here — headline → antithesis ladder →
    # aspects for a pair never seen whole — on measurement: coherent first
    # tetrads 42/80 against the staged 14/40 on the same free utterances,
    # genuine antitheses 74/80 against 27/40, ~43 s against ~55 s, replicated
    # (docs/dev-notes/antithesis-selection.md, "The one-shot build"). The
    # staged path still serves `ingest` (many theses from a document) and the
    # Analyst's `AnalysisPipeline(thesis_hashes=)`.
    #
    # The material is the person's turn, kept as an Input above, when there is
    # one; off the turn (a note planted later carries its own turn; a closing's
    # anchor on an empty graph has none) there is no material and the pinned
    # thesis plus `context` — the model's particulars — is what the call reads.
    from dialectical_framework.agents.analyst.skills.sketch_tetrad import \
        SketchTetrad

    skill = SketchTetrad(input_hashes=input_hashes, thesis=thesis, context=context)
    await skill.resolve()
    skill.report.artifacts.update(source_artifacts)
    return str(skill.report)
