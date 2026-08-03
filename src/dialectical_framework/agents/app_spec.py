"""
AppSpec: declarative app definition — the host describes WHAT its app is,
each agent head composes the right preamble from it.

Without this, an app developer must know framework lore to preamble an app:
which base constant belongs to which head (NAVIGATOR_APP for Analyst/Explorer,
NAVIGATOR_APP_EXPLORER_AGENT_COUNSELOR_REGISTER for the counsel toggle, bare persona for a standalone
Advisor), that later preamble sections override earlier ones, and that the
same tool guide must be repeated into every head's preamble. AppSpec owns
that lore: the app supplies only its custom pieces, the framework supplies
the generic contract.

Usage:
    ASTRO_APP = AppSpec(
        voicing=\"\"\"## Astrological Voicing
        Phrase oppositions in elemental and zodiacal terms where natural...\"\"\",
        advisor_persona=\"\"\"## Persona
        You are a wise astrologer. The person seeks counsel through their chart...\"\"\",
        tool_guide=\"\"\"## Chart Resources
        - lookup_natal_chart(person): fetch a natal chart. Use when...\"\"\",
        tools=[lookup_natal_chart],
    )

    Analyst(app=ASTRO_APP)
    Explorer(nexus_hash=nx, messages=msgs, app=ASTRO_APP)
    Advisor(nexus_hash=nx, messages=msgs, app=ASTRO_APP)   # counsel toggle
    Advisor(app=ASTRO_APP)                                  # standalone advisor

Every field is optional — an AppSpec with only `voicing` is a pure
re-skinning of the Navigator; one with only `tools` + `tool_guide` adds
domain resources without touching voice. The low-level `app_preamble` /
`app_tools` constructor params remain for full manual control; passing
both `app` and either of them raises (ambiguous composition).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class AppSpec:
    """Declarative definition of a host app, composed per agent head.

    voicing: Domain flavor layered on the Navigator user contract
        (Analyst/Explorer and the counsel toggle). Vocabulary direction,
        framing, domain emphasis — NOT tool docs, NOT persona for the
        standalone Advisor.
    advisor_persona: Persona for the STANDALONE (unscoped) Advisor, where
        the machinery is hidden and the preamble is the entire user-facing
        identity (like COUNSELOR_PERSONA). Ignored in counsel-toggle mode,
        which keeps the Navigator contract.
    tool_guide: Shared documentation for the app's tools — what each does,
        when to reach for it. Included verbatim in EVERY head's preamble
        so the usage rules cannot drift between heads. How tool use
        SURFACES to the user still follows each head's disclosure rules.
    tools: App-provided @llm.tool functions, passed to every head
        (see toolsets.merge_app_tools).
    """

    voicing: Optional[str] = None
    advisor_persona: Optional[str] = None
    tool_guide: Optional[str] = None
    tools: list = field(default_factory=list)

    def navigator_preamble(self, advanced: bool = False) -> str:
        """Preamble for Analyst/Explorer heads: Navigator contract + app pieces."""
        from dialectical_framework.agents.apps import (
            NAVIGATOR_APP_ADVANCED_TOGGLE, NAVIGATOR_APP)

        base = NAVIGATOR_APP_ADVANCED_TOGGLE if advanced else NAVIGATOR_APP
        return _join(base, self.voicing, self.tool_guide)

    def advisor_preamble(self, scoped: bool) -> str:
        """Preamble for the Advisor head.

        scoped=True (counsel toggle of a Navigator session): the Navigator
        contract survives the toggle — NAVIGATOR_APP_EXPLORER_AGENT_COUNSELOR_REGISTER + app pieces.
        scoped=False (standalone Advisor): the persona IS the identity —
        no Navigator base, machinery stays hidden.
        """
        from dialectical_framework.agents.apps import NAVIGATOR_APP_EXPLORER_AGENT_COUNSELOR_REGISTER

        if scoped:
            return _join(NAVIGATOR_APP_EXPLORER_AGENT_COUNSELOR_REGISTER, self.voicing, self.tool_guide)
        return _join(self.advisor_persona, self.tool_guide)


def _join(*parts: Optional[str]) -> str:
    return "\n\n".join(p.strip() for p in parts if p and p.strip())


def resolve_app_layer(
    app: Optional[AppSpec],
    app_preamble: Optional[str],
    app_tools: Optional[list],
    preamble_for: str,  # "navigator" | "advisor_scoped" | "advisor_unscoped"
) -> tuple[Optional[str], Optional[list]]:
    """Resolve the (preamble, tools) pair from either an AppSpec or the
    low-level params. Mixing both raises — composition would be ambiguous
    (does app_preamble replace the spec's derived preamble or stack on it?).
    """
    if app is None:
        return app_preamble, app_tools
    if app_preamble is not None or app_tools is not None:
        raise ValueError(
            "Pass either app= (declarative) or app_preamble=/app_tools= "
            "(manual), not both."
        )
    if preamble_for == "navigator":
        preamble = app.navigator_preamble()
    elif preamble_for == "advisor_scoped":
        preamble = app.advisor_preamble(scoped=True)
    elif preamble_for == "advisor_unscoped":
        preamble = app.advisor_preamble(scoped=False)
    else:
        raise ValueError(f"Unknown preamble_for: {preamble_for}")
    return preamble or None, app.tools or None
