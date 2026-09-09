"""
record_decision tool: persist a decision the person explicitly confirmed.

The ceremony lives in conversation (propose → read back → confirm) — this
tool is called only AFTER the person's explicit yes, with the confirmed
wording passed literally. Retracting or replacing a recorded decision goes
through the standard `discard` tool (reason referencing the new decision).

Provenance: WHO confirmed is a host-attested fact, closed over at tool
construction (Advisor(principal=...)) — never an LLM-supplied parameter.
"human" (the default) means an actual person confirmed the wording; a
delegated driver (agent-to-agent runs) must be constructed with its own
identity, else the ledger and inspect_node would present machine-authored
rationales as the person's own confirmed "why".
"""

from __future__ import annotations

from typing import Annotated

from mirascope import llm
from pydantic import Field

from dialectical_framework.concerns.record_decision import GroundLink
from dialectical_framework.utils.progress import progress_key


def _progress_key(question: str, stance: str) -> str:
    """A stable, opaque id for ONE record_decision call's progress stream.

    Same construction and the same two reasons as `anchor._progress_key`:
    content-derived so it survives a retry of the same call, and HASHED so a host
    that renders the key verbatim cannot turn it into a label quoting the person's
    own confirmed wording — which on this path is the most sensitive text in the
    system, since it is the decision they just committed to.
    """
    return progress_key(question, stance)


def build_record_decision(principal: str = "human"):
    """Build the record_decision tool with the confirming principal
    closed over (same code-not-prompt enforcement as the nexus pin in
    scoped.py)."""

    attested_principal = principal

    @llm.tool
    async def record_decision(
        question: Annotated[
            str,
            Field(description="The question that was being decided, in the person's confirmed words"),
        ],
        stance: Annotated[
            str,
            Field(description="The stance the person committed to, in their confirmed words"),
        ],
        rationale: Annotated[
            str,
            Field(
                description="The distilled why behind the decision as the person confirmed it, "
                "including reasons that live outside the mapped structure (deadlines, "
                "people, external facts)"
            ),
        ],
        grounds: Annotated[
            list[GroundLink] | None,
            Field(
                description="Nodes this decision rests on: {hash, role?} each. "
                "role='accepted_cost' for the risk the person confronted and accepted: "
                "the CHOSEN side's minus aspect (T- if they chose the thesis, A- if the "
                "antithesis) — a minus is a risk, whereas a plus is a goal or an "
                "obligation and is never a cost; role='adopted_pathway' for the pathway "
                "adopted as the ongoing recipe; omit role for a plain ground (tensions "
                "weighed, arrangements counseled from)."
            ),
        ] = None,
    ) -> str:
        """Record a decision the person has EXPLICITLY confirmed in conversation. Never call this silently or speculatively — propose the distilled record first, read it back, and record only on their clear yes. But their yes OBLIGES the call: when they have said to write it down, or have confirmed the record you read back, this call is what writing it down MEANS. Stating the decision in your reply — however well formatted, under any heading — is a message that ends with the conversation, and leaves them believing in a record they do not have. If you are about to present a settled decision in prose, call this in the SAME turn. Links the decision to the graph nodes that grounded it and attaches the confirmed rationale. To replace or retract a recorded decision, use `discard` on it (with a reason naming the newer decision if one replaces it)."""
        from dialectical_framework.concerns.record_decision import RecordDecision
        from dialectical_framework.utils.progress import progress_scope

        # Installed at the TOOL like `anchor` and `ingest`, but for a different
        # reason: there is no gather here, so nothing forces the placement. It sits
        # here because this is the boundary where a PERSON is waiting — the concern
        # is public and a host may call it outside any conversation, where a
        # progress stream has nobody to speak to.
        #
        # An in-band refusal (empty stance, an unresolvable ground) returns before
        # the concern declares its step, so the closing event is 0/0. That is the
        # honest reading: nothing was done, and the report carries the reason.
        with progress_scope("decision", key=_progress_key(question, stance)):
            # Mirascope passes json.loads'd kwargs without coercing nested models,
            # so `grounds` arrives as raw dicts — RecordDecision.resolve normalizes
            # them (single owner of that normalization) and refuses in-band on bad
            # input.
            concern = RecordDecision()
            await concern.resolve(
                question=question,
                stance=stance,
                rationale=rationale,
                grounds=grounds,
                principal=attested_principal,
            )
            return str(concern.report)

    return record_decision


# Default build: a human principal. Kept module-level so existing imports
# (toolset builders, tests) stay valid; hosts with a non-human driver pass
# principal= at Advisor construction instead of importing this.
record_decision = build_record_decision()
