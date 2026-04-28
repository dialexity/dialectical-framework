"""
ActionExtraction: Concern for generating Ac+ candidates along the Insight axis.

Generates Ac+ candidates (T- → A+ transitions) at different Insight levels,
allowing exploration of various transformation depths.

Usage:
    service = ActionExtraction()
    candidates = await service.resolve(pp, input_text, not_like_these=existing)
    for c in candidates:
        print(f"{c.insight_label}: {c.statement}")
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.agents.reasonable_concern import \
    ReasonableConcern
from dialectical_framework.agents.execution_report import ExecutionReport
from dialectical_framework.concerns.ac_re_taxonomy import (
    AC_PLUS_APEX_TARGET, insight_label_to_value, proactiveness_label_to_value)
from dialectical_framework.protocols.has_config import SettingsAware

# Insight hierarchy categories for exploration
# Groups insight levels into categories for generating candidates at different depths
INSIGHT_CATEGORIES = {
    "Generative": {
        "description": "High depth insight - strategic or transformational actions",
        "levels": [
            "Leverage",
            "Anticipation",
            "Inversion",
            "Redirection",
            "Transcendence",
        ],
    },
    "Configurational": {
        "description": "Medium depth insight - restructuring or combining approaches",
        "levels": ["Composition", "Reformulation"],
    },
    "Corrective": {
        "description": "Low depth insight - adjustments or reactive responses",
        "levels": ["Variation", "Tuning", "Procedure", "Reflex"],
    },
}

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.transformation import Transformation
    from dialectical_framework.graph.nodes.perspective import Perspective


SYSTEM_PROMPT = """You are an expert in dialectical reasoning, specializing in Action-Reflection transformations.

Your task is to generate Ac+ candidates that represent T- → A+ transition paths.

## What is Ac+?

The +/- notation is STRUCTURAL (like electrical charges), not a value judgment:
- "+" aspects target beneficial states (T+ or A+)
- "-" aspects target problematic states (T- or A-)

Ac+ is an "action targeting A+" - a way of acting/behaving that helps someone escape the problematic aspects of the thesis (T-) and move toward the healthy aspects of the antithesis (A+).

## Y-Axis: Insight (0.0 → 1.0)

The Insight scale is hierarchical:

```
APEX
├── GENERATIVE
│   ├── Transformational
│   │   ├── Transcendence (1.0) - Paradigm shift, new dimension
│   │   ├── Redirection (0.9) - Fundamental change of direction
│   │   └── Inversion (0.8) - Flipping perspective entirely
│   └── Strategic
│       ├── Anticipation (0.7) - Acting/thinking ahead of events
│       └── Leverage (0.6) - Finding and using leverage points
├── CONFIGURATIONAL
│   ├── Composition (0.5) - Combining elements in new ways
│   └── Reformulation (0.4) - Restating/restructuring approach
└── CORRECTIVE
    ├── Adjusted
    │   ├── Variation (0.3) - Making deliberate small changes
    │   └── Tuning (0.2) - Fine-tuning existing approach
    └── Reactive
        ├── Procedure (0.1) - Following established protocol
        └── Reflex (0.0) - Automatic, instinctive response
```

## X-Axis: Proactiveness - Actions (0.5 → 1.0)

| Value | Label | Description |
|-------|-------|-------------|
| 0.5   | Coordination | Aligning multiple elements |
| 0.6   | Intervention | Stepping in to change something ← APEX |
| 0.7   | Implementation | Executing a defined plan |
| 0.8   | Configuration | Arranging/structuring elements |
| 0.9   | Governance | Directing, setting rules/policies |
| 1.0   | Stewardship | Active long-term caretaking |

## Requirements for Ac+ statements

1. Must describe an ACTION (what to DO), not a reflection or observation
2. Must help transition FROM T- (problem) TOWARD A+ (benefit)
3. Must NOT simply restate A+ - it's the PATH, not the destination
4. Should be generative: enable discovery rather than prescribe specific outcomes
5. Length: 1-15 words, actionable and memorable
6. Choose the insight level that best matches the nature of the action
"""


class ActionCandidateDto(BaseModel):
    """A candidate Ac+ statement with coordinates."""

    headline: str = Field(description="Short headline (component length)")
    statement: str = Field(description="The Ac+ statement (1-15 words)")
    insight_label: str = Field(
        description="Insight level: leverage/anticipation/composition/etc"
    )
    proactiveness_label: str = Field(
        description="Action category: coordination/intervention/implementation/etc"
    )
    explanation: str = Field(description="How this action helps transition T- → A+")


class ActionCandidateResultDto(BaseModel):
    """Container for an Ac+ candidate with numeric coordinates."""

    headline: str
    statement: str
    insight: float
    proactiveness: float
    insight_label: str
    proactiveness_label: str
    explanation: str


class ActionExtraction(
    ReasonableConcern[list[ActionCandidateResultDto]], SettingsAware
):
    """
    Concern for extracting Ac+ candidates at various Insight levels.

    Generates multiple Ac+ candidates along the Y-axis (Insight), with the LLM
    determining the appropriate X-axis position (Proactiveness) for each.
    """

    def __init__(self) -> None:
        self._conversation = ConversationFacilitator()

    async def resolve(
        self,
        pp: Perspective,
        input_text: str = "",
        not_like_these: Optional[list[Transformation]] = None,
    ) -> list[ActionCandidateResultDto]:
        """
        Extract Ac+ candidates for a Perspective.

        Args:
            pp: The Perspective to generate candidates for (must be complete)
            input_text: Optional source content context
            not_like_these: Existing transformations to avoid duplicating

        Returns:
            List of ActionCandidateResultDto with statements and coordinates
        """
        self._report = ExecutionReport(tool=self.__class__.__name__)

        if not pp.is_complete():
            raise ValueError("Perspective must have all 6 positions to extract actions")

        # Initialize conversation
        self._conversation.set_system_prompt(SYSTEM_PROMPT)

        # Get PP context
        pp_context = self._build_pp_context(pp)

        # Build exclusion list
        exclusion_statements = self._build_exclusion_list(not_like_these or [])

        # Generate candidates in parallel - one per hierarchy category
        tasks = [
            self._generate_candidate_for_category(
                pp_context, input_text, category, info, exclusion_statements
            )
            for category, info in INSIGHT_CATEGORIES.items()
        ]
        candidates = await asyncio.gather(*tasks)

        # Convert to results with numeric coordinates
        results = [self._to_result_dto(c) for c in candidates if c is not None]

        # Filter out any that match exclusions
        results = [r for r in results if r.statement not in exclusion_statements]

        # Report artifacts
        self._report.artifacts["pp_hash"] = pp.short_hash
        self._report.artifacts["candidate_count"] = len(results)
        self._report.artifacts["insight_categories"] = list(INSIGHT_CATEGORIES.keys())
        self._report.summary = (
            f"Extracted {len(results)} Ac+ candidates for PP {pp.short_hash}"
        )

        return results

    def _build_pp_context(self, pp: Perspective) -> str:
        """Build context string from Perspective components."""
        parts = []

        positions = [
            ("T", pp.t),
            ("T+", pp.t_plus),
            ("T-", pp.t_minus),
            ("A", pp.a),
            ("A+", pp.a_plus),
            ("A-", pp.a_minus),
        ]

        for name, manager in positions:
            result = manager.get()
            if result:
                comp, _ = result
                parts.append(f"{name}: {comp.statement}")

        return "\n".join(parts)

    def _build_exclusion_list(self, transformations: list[Transformation]) -> list[str]:
        """Extract Ac+ statements from existing transformations to avoid."""
        exclusions = []
        for t in transformations:
            ac_plus_result = t.ac_plus.get()
            if ac_plus_result:
                transition, _ = ac_plus_result
                target_result = transition.target.get()
                if target_result:
                    comp, _ = target_result
                    exclusions.append(comp.statement)
        return exclusions

    async def _generate_candidate_for_category(
        self,
        pp_context: str,
        input_text: str,
        category: str,
        category_info: dict,
        exclusions: list[str],
    ) -> Optional[ActionCandidateDto]:
        """Generate a single Ac+ candidate for an insight category."""
        context_section = (
            f"<context>\n{input_text}\n</context>\n\n" if input_text else ""
        )

        exclusion_section = ""
        if exclusions:
            exclusion_list = "\n".join(f"- {s}" for s in exclusions)
            exclusion_section = f"""
<avoid_similar_to>
{exclusion_list}
</avoid_similar_to>

Generate something DIFFERENT from the statements above.
"""

        levels_str = ", ".join(category_info["levels"])
        prompt = f"""{context_section}Given this Perspective:

<perspective>
{pp_context}
</perspective>
{exclusion_section}
Generate an Ac+ (Positive Action) statement at the **{category.upper()}** insight level.

{category}: {category_info["description"]}
Valid insight labels for this category: {levels_str}

The Ac+ must:
1. Be an ACTION that helps escape T- and move toward A+
2. Pick the specific insight label from [{levels_str}] that best fits your action
3. Choose the appropriate action category (Coordination/Intervention/Implementation/Configuration/Governance/Stewardship)
4. Provide a short headline (~{self.settings.component_length} words) - the essence of the action
5. Provide a fuller statement/summary (1-15 words) - actionable and memorable

Focus on the T- → A+ transition path, not the destination."""

        try:
            return await self._conversation.isolate().submit(
                response_model=ActionCandidateDto,
                user_content=prompt,
            )
        except Exception:
            return None

    def _to_result_dto(self, candidate: ActionCandidateDto) -> ActionCandidateResultDto:
        """Convert candidate to result DTO with numeric coordinates."""
        insight_label = candidate.insight_label.capitalize()
        proactiveness_label = candidate.proactiveness_label.capitalize()

        # Get numeric values, default to Ac+ apex targets if label not recognized
        try:
            insight = insight_label_to_value(insight_label)
        except ValueError:
            insight = AC_PLUS_APEX_TARGET["insight"]

        try:
            proactiveness = proactiveness_label_to_value(proactiveness_label)
        except ValueError:
            proactiveness = AC_PLUS_APEX_TARGET["proactiveness"]

        return ActionCandidateResultDto(
            headline=candidate.headline,
            statement=candidate.statement,
            insight=insight,
            proactiveness=proactiveness,
            insight_label=insight_label,
            proactiveness_label=proactiveness_label,
            explanation=candidate.explanation,
        )
