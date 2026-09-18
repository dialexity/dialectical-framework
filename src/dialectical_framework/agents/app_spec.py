"""
AppSpec: declarative app definition — the host describes WHAT its app is,
each agent head composes the right preamble from it.

Without this, an app developer must know framework lore to preamble an app:
which base constant belongs to which head (NAVIGATOR_APP for Analyst/Explorer,
NAVIGATOR_APP_EXPLORER_AGENT_ADVISORY_REGISTER for the advisory toggle, bare persona for a standalone
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
    Advisor(nexus_hash=nx, messages=msgs, app=ASTRO_APP)   # advisory toggle
    Advisor(app=ASTRO_APP)                                  # standalone advisor

    # Expert register for a user who knows the framework: the SAME AppSpec plus
    # one flag, and it CARRIES ACROSS the Explorer<->advisory toggle.
    Explorer(nexus_hash=nx, messages=msgs, app=ASTRO_APP, advanced=True)
    Advisor(nexus_hash=nx, messages=msgs, app=ASTRO_APP, advanced=True)

`advanced` is deliberately NOT an AppSpec field: it is a per-session property of
the person on the other end (they understand the framework), not of the product,
so one AppSpec serves both registers. It is honoured only where an AppSpec
composes the preamble, and raises anywhere it could not be — with app_preamble=
you own the preamble, and for the standalone Advisor there is no framework
vocabulary to unlock.

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
        (Analyst/Explorer and the advisory toggle). Vocabulary direction,
        framing, domain emphasis — NOT tool docs, NOT persona for the
        standalone Advisor.
    advisor_persona: Persona for the STANDALONE (unscoped) Advisor, where
        the machinery is hidden and the preamble is the entire user-facing
        identity (like COUNSELOR_PERSONA). Ignored in advisory-toggle mode,
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

    def advisor_preamble(self, scoped: bool, advanced: bool = False) -> str:
        """Preamble for the Advisor head.

        scoped=True (advisory toggle of a Navigator session): the Navigator
        contract survives the toggle — NAVIGATOR_APP_EXPLORER_AGENT_ADVISORY_REGISTER + app pieces.
        scoped=False (standalone Advisor): the persona IS the identity —
        no Navigator base, machinery stays hidden.

        advanced CARRIES THROUGH the toggle (scoped only): an expert who
        toggled from an advanced Explorer keeps framework vocabulary, hashes
        and numeric scores in advisory mode — same literal history, so dropping
        back to translated vocabulary mid-conversation would read as the head
        forgetting who it is talking to. It RAISES for the standalone Advisor,
        which has no framework vocabulary to unlock (see resolve_app_layer).
        """
        from dialectical_framework.agents.apps import (
            NAVIGATOR_APP_EXPLORER_AGENT_ADVISORY_REGISTER,
            NAVIGATOR_APP_EXPLORER_AGENT_ADVISORY_REGISTER_ADVANCED)

        if scoped:
            base = (
                NAVIGATOR_APP_EXPLORER_AGENT_ADVISORY_REGISTER_ADVANCED
                if advanced
                else NAVIGATOR_APP_EXPLORER_AGENT_ADVISORY_REGISTER
            )
            return _join(base, self.voicing, self.tool_guide)
        if advanced:
            raise ValueError(_ADVANCED_UNSCOPED_ADVISOR)
        return _join(self.advisor_persona, self.tool_guide)


def _join(*parts: Optional[str]) -> str:
    return "\n\n".join(p.strip() for p in parts if p and p.strip())


_ADVANCED_UNSCOPED_ADVISOR = (
    "advanced=True has no meaning for a standalone Advisor: that head hides "
    "the machinery, so there is no framework vocabulary to unlock. Advanced "
    "mode belongs to the Navigator heads (Analyst, Explorer) and to the "
    "advisory toggle (Advisor(nexus_hash=...))."
)

_ADVANCED_WITHOUT_SPEC = (
    "advanced=True selects an AppSpec-composed preamble, and there is no app= "
    "to compose from. With app_preamble= you own the preamble: pass "
    "AppSpec.navigator_preamble(advanced=True) or "
    "AppSpec.advisor_preamble(scoped=True, advanced=True) — or the "
    "NAVIGATOR_APP_ADVANCED_TOGGLE / "
    "NAVIGATOR_APP_EXPLORER_AGENT_ADVISORY_REGISTER_ADVANCED constant — "
    "yourself, together with app_tools=."
)


def resolve_app_layer(
    app: Optional[AppSpec],
    app_preamble: Optional[str],
    app_tools: Optional[list],
    preamble_for: str,  # "navigator" | "advisor_scoped" | "advisor_unscoped"
    advanced: bool = False,
) -> tuple[Optional[str], Optional[list]]:
    """Resolve the (preamble, tools) pair from either an AppSpec or the
    low-level params. Mixing both raises — composition would be ambiguous
    (does app_preamble replace the spec's derived preamble or stack on it?).

    advanced is a per-SESSION host toggle (this user knows the framework), not
    a property of the app — hence a constructor argument on the heads rather
    than an AppSpec field. It is honoured only where an AppSpec composes the
    preamble; everywhere else it RAISES rather than being ignored, because a
    silently-dropped advanced flag is what this parameter exists to fix (it was
    unreachable through app= until 2026-09-16, and the manual workaround the
    code recommended dropped the app's tools without saying so).
    """
    if advanced and preamble_for == "advisor_unscoped":
        raise ValueError(_ADVANCED_UNSCOPED_ADVISOR)
    if app is None:
        if advanced:
            raise ValueError(_ADVANCED_WITHOUT_SPEC)
        return app_preamble, app_tools
    if app_preamble is not None or app_tools is not None:
        raise ValueError(
            "Pass either app= (declarative) or app_preamble=/app_tools= "
            "(manual), not both."
        )
    if preamble_for == "navigator":
        preamble = app.navigator_preamble(advanced=advanced)
    elif preamble_for == "advisor_scoped":
        preamble = app.advisor_preamble(scoped=True, advanced=advanced)
    elif preamble_for == "advisor_unscoped":
        preamble = app.advisor_preamble(scoped=False)
    else:
        raise ValueError(f"Unknown preamble_for: {preamble_for}")
    return preamble or None, app.tools or None
