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
                "role='accepted_cost' for the unchosen side's contribution the person "
                "confronted and accepted; role='adopted_pathway' for the pathway adopted "
                "as the ongoing recipe; omit role for a plain ground (tensions weighed, "
                "arrangements counseled from)."
            ),
        ] = None,
    ) -> str:
        """Record a decision the person has EXPLICITLY confirmed in conversation. Never call this silently or speculatively — propose the distilled record first, read it back, and record only on their clear yes. Links the decision to the graph nodes that grounded it and attaches the confirmed rationale. To replace or retract a recorded decision, use `discard` on it (with a reason naming the newer decision if one replaces it)."""
        from dialectical_framework.concerns.record_decision import RecordDecision

        # Mirascope passes json.loads'd kwargs without coercing nested models, so
        # `grounds` arrives as raw dicts — RecordDecision.resolve normalizes them
        # (single owner of that normalization) and refuses in-band on bad input.
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
