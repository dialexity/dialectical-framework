"""
Tests for AppSpec — the declarative app definition.

The host describes WHAT its app is (voicing, persona, tool guide, tools);
each agent head composes the right preamble: Navigator heads get
NAVIGATOR_APP + voicing + tool_guide, the counsel toggle gets
EXPLORATION_ADVISOR_APP + voicing + tool_guide, the standalone Advisor gets
advisor_persona + tool_guide. The framework owns the composition lore so
apps supply only their custom pieces.
"""

from __future__ import annotations

import pytest
from mirascope import llm

from dialectical_framework.agents.app_spec import AppSpec

VOICING = "## Astro Voicing\nPhrase oppositions elementally."
PERSONA = "## Persona\nYou are a wise astrologer."
TOOL_GUIDE = "## Chart Resources\nlookup_natal_chart: use when a birth date is known."


@llm.tool
async def lookup_natal_chart(person: str) -> str:
    """Look up the natal chart for a person."""
    return f"chart for {person}"


FULL_SPEC = AppSpec(
    voicing=VOICING,
    advisor_persona=PERSONA,
    tool_guide=TOOL_GUIDE,
    tools=[lookup_natal_chart],
)


class TestAppSpecComposition:
    def test_navigator_preamble_composes_on_navigator_app(self):
        from dialectical_framework.agents.apps import NAVIGATOR_APP

        preamble = FULL_SPEC.navigator_preamble()
        assert preamble.startswith(NAVIGATOR_APP.strip())
        assert VOICING in preamble
        assert TOOL_GUIDE in preamble
        # Navigator heads never get the standalone-advisor persona
        assert PERSONA not in preamble

    def test_navigator_preamble_advanced_mode(self):
        from dialectical_framework.agents.apps import \
            NAVIGATOR_ADVANCED_MODE_APP

        preamble = FULL_SPEC.navigator_preamble(advanced=True)
        assert preamble.startswith(NAVIGATOR_ADVANCED_MODE_APP.strip())
        assert VOICING in preamble

    def test_advisor_scoped_keeps_navigator_contract(self):
        from dialectical_framework.agents.apps import EXPLORATION_ADVISOR_APP

        preamble = FULL_SPEC.advisor_preamble(scoped=True)
        assert preamble.startswith(EXPLORATION_ADVISOR_APP.strip())
        assert VOICING in preamble
        assert TOOL_GUIDE in preamble
        assert PERSONA not in preamble  # counsel toggle is NOT the standalone persona

    def test_advisor_unscoped_is_persona_only(self):
        from dialectical_framework.agents.apps import (EXPLORATION_ADVISOR_APP,
                                                       NAVIGATOR_APP)

        preamble = FULL_SPEC.advisor_preamble(scoped=False)
        assert preamble.startswith(PERSONA)
        assert TOOL_GUIDE in preamble
        # standalone advisor hides the machinery — no Navigator contract
        assert NAVIGATOR_APP.strip() not in preamble
        assert EXPLORATION_ADVISOR_APP.strip() not in preamble
        assert VOICING not in preamble  # voicing is Navigator-side flavor

    def test_tool_guide_identical_in_every_head(self):
        """The usage rules cannot drift between heads: same block verbatim."""
        for preamble in (
            FULL_SPEC.navigator_preamble(),
            FULL_SPEC.advisor_preamble(scoped=True),
            FULL_SPEC.advisor_preamble(scoped=False),
        ):
            assert TOOL_GUIDE in preamble

    def test_empty_spec_yields_bare_bases(self):
        from dialectical_framework.agents.apps import NAVIGATOR_APP

        spec = AppSpec()
        assert spec.navigator_preamble() == NAVIGATOR_APP.strip()
        assert spec.advisor_preamble(scoped=False) == ""


class TestAgentsAcceptAppSpec:
    def test_analyst_composes_from_spec(self):
        from dialectical_framework.agents.analyst.analyst import Analyst
        from dialectical_framework.agents.apps import NAVIGATOR_APP

        analyst = Analyst(app=FULL_SPEC)
        prompt = _system_prompt_text(analyst)
        assert VOICING in prompt
        assert TOOL_GUIDE in prompt
        assert NAVIGATOR_APP.strip()[:80] in prompt
        assert "lookup_natal_chart" in [t.__name__ for t in analyst._tools]

    def test_advisor_unscoped_composes_persona(self):
        from dialectical_framework.agents.advisor.advisor import Advisor

        advisor = Advisor(app=FULL_SPEC)
        prompt = _system_prompt_text(advisor)
        assert PERSONA in prompt
        assert VOICING not in prompt
        assert "lookup_natal_chart" in [t.__name__ for t in advisor._tools]

    def test_explorer_and_scoped_advisor_compose_from_spec(self):
        from dialectical_framework.agents.advisor.advisor import Advisor
        from dialectical_framework.agents.apps import EXPLORATION_ADVISOR_APP
        from dialectical_framework.agents.explorer.explorer import Explorer
        from dialectical_framework.graph.nodes.case import Case
        from dialectical_framework.graph.nodes.nexus import Nexus
        from dialectical_framework.graph.scope_context import scope

        case = Case()
        case.commit()
        with scope(case.sid):
            nexus = Nexus(intent="app spec test")
            nexus.save()
            nexus.commit()

            explorer = Explorer(nexus_hash=nexus.hash[:7], app=FULL_SPEC)
            assert VOICING in _system_prompt_text(explorer)
            assert "lookup_natal_chart" in [
                t.__name__ for t in explorer._tools
            ]

            advisor = Advisor(
                nexus_hash=nexus.hash[:7],
                dialectical_context="dump",
                app=FULL_SPEC,
            )
            prompt = _system_prompt_text(advisor)
            assert EXPLORATION_ADVISOR_APP.strip()[:80] in prompt
            assert VOICING in prompt
            assert PERSONA not in prompt

    def test_mixing_app_and_manual_params_raises(self):
        from dialectical_framework.agents.analyst.analyst import Analyst

        with pytest.raises(ValueError, match="not both"):
            Analyst(app=FULL_SPEC, app_preamble="manual")
        with pytest.raises(ValueError, match="not both"):
            Analyst(app=FULL_SPEC, app_tools=[lookup_natal_chart])

    def test_manual_params_still_work_without_spec(self):
        from dialectical_framework.agents.analyst.analyst import Analyst

        analyst = Analyst(
            app_preamble="manual preamble", app_tools=[lookup_natal_chart]
        )
        assert "manual preamble" in _system_prompt_text(analyst)
        assert "lookup_natal_chart" in [t.__name__ for t in analyst._tools]


def _system_prompt_text(agent) -> str:
    content = agent._conversation._messages[0].content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(getattr(part, "text", str(part)) for part in content)
    return content.text
