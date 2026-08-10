"""Relationship model for Rationale explaining an entity."""
from __future__ import annotations

from typing import Optional

from dialectical_framework.graph.relationships.immutable_structure import AnalyticalStructure

#: `ExplainsRelationship.role` for a rationale holding the case particulars a
#: tetrad was abstracted FROM — the evidence, not an assessment of it.
#:
#: The tetrad's own text is universal by construction: `component_length` caps
#: poles and aspects near seven words, `commit()` dedups matching wording into
#: one shared node, and taxonomy anchoring pulls them toward `SYSTEMIC_TAXONOMY`
#: apexes. That abstraction is the point — it is what makes a tetrad
#: transferable — but it discards what the abstraction came from. "Solo
#: leadership enables faster decisive execution" no longer knows that this
#: founder holds 55%, gave feedback in March, and sat through three customer
#: calls as a plus-one.
#:
#: Measured cost: across six live counsel sessions the graph carried 0 of 15
#: case particulars while a plain LLM keeping its own session notes carried 11
#: of 15. At the returning-session wobble the framework contradicted its own
#: record ("This isn't the accepted cost resurfacing") because it held no fact
#: to check the panic against; the bare LLM, holding "cofounder isn't a
#: rainmaker; customers won't follow him out", asked whether the person had
#: known all along. They had.
#:
#: Why a role on the edge rather than a field on Perspective: grounding
#: ACCRETES (the person reveals more three turns later). A Perspective field
#: would have to be mutated, and `Perspective.intent` — the only existing
#: free-text slot — is hash-participating (`base_node.compute_hash`) AND the
#: discriminator between sibling tetrads on one Polarity, so writing case facts
#: there both raises `ImmutableNodeError` at `save()` and corrupts tetrad
#: identity. Appending a Rationale per turn sidesteps mutation entirely and
#: yields a chronology of what was revealed when, which one flat field cannot.
#:
#: Why not `Rationale.agent`: that field is provenance — `<provider>/<model>`,
#: with `"human"` reserved for content a PERSON confirmed verbatim. Grounding
#: text is model-composed from what the person said, so tagging it "human"
#: would claim an attestation nobody made. Role says what the rationale IS;
#: `agent` keeps saying who wrote it. Both stay honest.
#:
#: Why not an Input: Input is generative — material there feeds thesis
#: extraction, so conversational particulars parked in it would manufacture
#: tensions nobody raised and sit permanently "pending analysis". Grounding is
#: read-only context for the conversation, never fuel for the pipeline.
#:
#: Scope is material-only: facts about the SITUATION. Facts about the PERSON
#: (tone, register, what push-back they respect) and forward-looking
#: conversational strategy ("watch for whether they are second-guessing") are
#: agent memory, not dialectical material — they belong to the host
#: application, and admitting them here would make the graph a general-purpose
#: notebook.
ROLE_GROUNDING = "grounding"


class ExplainsRelationship(AnalyticalStructure, type="EXPLAINS"):
    """
    Links a Rationale to the AssessableEntity it explains.

    Part of the analytical layer - connects explanatory artifacts
    to the entities they analyze. Target stored in Rationale's data.

    Properties:
        role: Optional semantic role of this explanation. Open vocabulary,
            following `GroundedInRelationship.role` — a role exists iff a
            consumer (renderer, prompt, query) branches on it; plain
            explanations carry None. Seed value:
            - `ROLE_GROUNDING` ("grounding"): the case particulars this
              entity was abstracted from. See the constant's docstring.

    Untagged explanations are machine assessment prose (control-statement
    checks, diagonal-opposition checks, causality reasoning) — the pre-existing
    population, which keeps `role=None` and keeps rendering exactly where it
    did before.
    """

    role: Optional[str] = None

