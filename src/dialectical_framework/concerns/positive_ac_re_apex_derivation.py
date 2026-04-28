"""
AcReApexDerivation: Concern for deriving Re+ and Ac+ apex statements for a Perspective.

The apex statements represent the reference transformation paths for this specific
Perspective context, against which other transformations are measured (via HS).

Apexes are generated within fixed coordinate ranges (sweet spots):
- Re+ apex: X (proactiveness) = 0.2-0.3, Y (insight) = 0.5-0.7
- Ac+ apex: X (proactiveness) = 0.5-0.7, Y (insight) = 0.5-0.7

Usage:
    service = AcReApexDerivation()
    apexes = await service.resolve(pp, input_text)
    print(f"Re+ apex: {apexes.re_plus_apex.statement}")
    print(f"Ac+ apex: {apexes.ac_plus_apex.statement}")
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.agents.reasonable_concern import \
    ReasonableConcern
from dialectical_framework.agents.execution_report import ExecutionReport
from dialectical_framework.concerns.ac_re_taxonomy import (
    AC_PLUS_APEX_TARGET, RE_PLUS_APEX_TARGET, insight_label_to_value,
    proactiveness_label_to_value)
from dialectical_framework.protocols.has_config import SettingsAware

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.perspective import Perspective


# Sweet spot margin around apex targets
SWEET_SPOT_MARGIN = 0.1


def _make_sweet_spot(target: dict[str, float]) -> dict[str, float]:
    """Derive sweet spot range from apex target coordinates."""
    return {
        "proactiveness_min": target["proactiveness"] - SWEET_SPOT_MARGIN,
        "proactiveness_max": target["proactiveness"] + SWEET_SPOT_MARGIN,
        "insight_min": target["insight"] - SWEET_SPOT_MARGIN,
        "insight_max": target["insight"] + SWEET_SPOT_MARGIN,
    }


# Sweet spot ranges derived from taxonomy apex targets
RE_PLUS_SWEET_SPOT = _make_sweet_spot(RE_PLUS_APEX_TARGET)
AC_PLUS_SWEET_SPOT = _make_sweet_spot(AC_PLUS_APEX_TARGET)


SYSTEM_PROMPT = f"""You are an expert in dialectical reasoning, specializing in Action-Reflection transformations.

Your task is to derive apex statements that represent reference transformation paths for a given Perspective.

## Transformation Structure

A Perspective is built around a Polarity (T, A) and adds four Aspects (T+, T-, A+, A-):
- T (Thesis): A neutral statement of one side
- T+: The healthy/productive form of T
- T-: The problematic/excessive form of T
- A (Antithesis): The opposing side
- A+: The healthy/productive form of A
- A-: The problematic/excessive form of A

Transformations navigate this tension through Action and Reflection:
- Ac+ (Positive Action): T- → A+ path (escaping T's problems toward A's benefits)
- Re+ (Positive Reflection): A- → T+ path (escaping A's problems toward T's benefits)

## Y-Axis: Insight (0.0 → 1.0)

```
APEX
├── GENERATIVE
│   ├── Transformational
│   │   ├── Transcendence (1.0) - Paradigm shift, new dimension
│   │   ├── Redirection (0.9) - Fundamental change of direction
│   │   └── Inversion (0.8) - Flipping perspective entirely
│   └── Strategic
│       ├── Anticipation (0.7) - Acting/thinking ahead of events
│       └── Leverage (0.6) - Finding and using leverage points ← SWEET SPOT
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

## X-Axis: Proactiveness (0.0 → 1.0)

**Reflections (Re+ = A- → T+, Re- = A+ → T-) — Apex zone: ~{RE_PLUS_APEX_TARGET["proactiveness"]}**

| Value | Label | Description |
|-------|-------|-------------|
| 0.0   | Observation | Passive noticing without judgment |
| 0.1   | Detection | Identifying patterns or anomalies |
| 0.2   | Interpretation | Making sense of what's detected ← APEX |
| 0.3   | Framing | Placing in broader context |
| 0.4   | Evaluation | Assessing value/significance ← MIDPOINT |

**Actions (Ac+ = T- → A+, Ac- = T+ → A-) — Apex zone: ~{AC_PLUS_APEX_TARGET["proactiveness"]}**

| Value | Label | Description |
|-------|-------|-------------|
| 0.5   | Coordination | Aligning multiple elements |
| 0.6   | Intervention | Stepping in to change something ← APEX |
| 0.7   | Implementation | Executing a defined plan |
| 0.8   | Configuration | Arranging/structuring elements |
| 0.9   | Governance | Directing, setting rules/policies |
| 1.0   | Stewardship | Active long-term caretaking |

## Ac → Re Polar Pairs (maps Action to complementary Reflection)

| Ac (Action) | Re (Reflection) | Tension |
|-------------|-----------------|---------|
| Coordination (0.5) | Framing (0.3) | Aligning ↔ Contextualizing |
| Intervention (0.6) | Interpretation (0.2) | Acting on ↔ Making sense ← APEX PAIR |
| Implementation (0.7) | Detection (0.1) | Executing ↔ Pattern recognition |
| Configuration (0.8) | Observation (0.0) | Structuring ↔ Passive witness |
| Governance (0.9) | Evaluation (0.4) | Directing ↔ Assessing |
| Stewardship (1.0) | Evaluation (0.4) | Caretaking ↔ Assessing |

## Apex Constructs

```
Ac+ Apex (Not-A)
├── Meaning: Affinity with A without instantiating A
├── Function: Enables non-coercive lean toward A+
└── Example (T=Love): "Decoupling by Default" → path to Autonomy

Re+ Apex (Not-T)
├── Meaning: Affinity with T without instantiating T
├── Function: Enables non-coercive lean toward T+
└── Example (T=Love): "Relational Value Relocation" → path to Bonding
```

## Sweet Spot Ranges (IMPORTANT)

You MUST generate apexes within these coordinate ranges:

**Re+ apex (Reflection):**
- Proactiveness (X): {RE_PLUS_SWEET_SPOT["proactiveness_min"]} - {RE_PLUS_SWEET_SPOT["proactiveness_max"]}
- Insight (Y): {RE_PLUS_SWEET_SPOT["insight_min"]} - {RE_PLUS_SWEET_SPOT["insight_max"]}
- Best labels: Interpretation/Framing + Composition/Leverage/Anticipation

**Ac+ apex (Action):**
- Proactiveness (X): {AC_PLUS_SWEET_SPOT["proactiveness_min"]} - {AC_PLUS_SWEET_SPOT["proactiveness_max"]}
- Insight (Y): {AC_PLUS_SWEET_SPOT["insight_min"]} - {AC_PLUS_SWEET_SPOT["insight_max"]}
- Best labels: Intervention/Implementation + Composition/Leverage/Anticipation

## Requirements for Apex Statements

1. Each apex should be 1-15 words, actionable and memorable
2. They should be complementary (Re+ and Ac+ work together)
3. They should NOT simply restate T+/A+ but describe the PATH to them
4. They should be generative (enabling discovery) not prescriptive
5. Choose labels that fall WITHIN the sweet spot ranges specified above

## Validation

Ac+/Re+ must: (1) not restate A+/T+, (2) be generative, (3) explain subtlety/non-force, (4) generalize beyond T/A.
"""


class ApexCandidateDto(BaseModel):
    """A candidate apex statement with coordinates."""

    statement: str = Field(description="The apex statement (1-15 words)")
    insight_label: str = Field(
        description="Insight label from taxonomy (e.g., leverage, composition, anticipation)"
    )
    proactiveness_label: str = Field(
        description="Proactiveness label from taxonomy (e.g., interpretation, intervention)"
    )
    explanation: str = Field(
        description="Why this statement represents the path and how it fits the sweet spot"
    )


class ApexPairDto(BaseModel):
    """Result of generating both Re+ and Ac+ apex candidates."""

    re_plus_apex: ApexCandidateDto = Field(
        description="Re+ apex: A- → T+ reflection path (proactiveness 0.2-0.3, insight 0.5-0.7)"
    )
    ac_plus_apex: ApexCandidateDto = Field(
        description="Ac+ apex: T- → A+ action path (proactiveness 0.5-0.7, insight 0.5-0.7)"
    )


class ApexDto(BaseModel):
    """Final apex with numeric coordinates."""

    statement: str
    insight: float  # Y-axis value
    proactiveness: float  # X-axis value
    insight_label: str
    proactiveness_label: str


class AcReApexDerivationResultDto(BaseModel):
    """Result container for apex derivation."""

    re_plus_apex: ApexDto
    ac_plus_apex: ApexDto


class AcReApexDerivation(
    ReasonableConcern[AcReApexDerivationResultDto], SettingsAware
):
    """
    Concern for deriving Re+ and Ac+ apex statements for a Perspective context.

    The derived apexes serve as reference points for calculating Heuristic Similarity (HS)
    of other transformation candidates. Apexes are constrained to sweet spot ranges.
    """

    def __init__(self) -> None:
        self._conversation = ConversationFacilitator()

    async def resolve(
        self,
        pp: Perspective,
        input_text: str = "",
    ) -> AcReApexDerivationResultDto:
        """
        Derive Re+ and Ac+ apex statements for a Perspective.

        Args:
            pp: The Perspective to derive apexes for (must be complete)
            input_text: Optional source content context

        Returns:
            AcReApexDerivationResultDto with Re+ and Ac+ apexes including coordinates
        """
        self._report = ExecutionReport(tool=self.__class__.__name__)

        if not pp.is_complete():
            raise ValueError("Perspective must have all 6 positions to derive apexes")

        # Initialize conversation
        self._conversation.set_system_prompt(SYSTEM_PROMPT)

        # Get PP context
        pp_context = self._build_pp_context(pp)

        # Generate apex pair
        apex_pair = await self._generate_apex_pair(pp_context, input_text)

        # Convert to result with numeric coordinates (clamped to sweet spots)
        re_plus_apex = self._to_apex_dto(apex_pair.re_plus_apex, RE_PLUS_SWEET_SPOT)
        ac_plus_apex = self._to_apex_dto(apex_pair.ac_plus_apex, AC_PLUS_SWEET_SPOT)

        result = AcReApexDerivationResultDto(
            re_plus_apex=re_plus_apex,
            ac_plus_apex=ac_plus_apex,
        )

        # Report artifacts
        self._report.artifacts["pp_hash"] = pp.short_hash
        self._report.artifacts["re_plus_apex"] = re_plus_apex.model_dump()
        self._report.artifacts["ac_plus_apex"] = ac_plus_apex.model_dump()
        self._report.summary = (
            f"Derived apexes for PP {pp.short_hash}: "
            f"Re+ ({re_plus_apex.proactiveness:.1f}, {re_plus_apex.insight:.1f}), "
            f"Ac+ ({ac_plus_apex.proactiveness:.1f}, {ac_plus_apex.insight:.1f})"
        )

        return result

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

    async def _generate_apex_pair(
        self,
        pp_context: str,
        input_text: str,
    ) -> ApexPairDto:
        """Generate Re+ and Ac+ apex candidates."""
        context_section = (
            f"<context>\n{input_text}\n</context>\n\n" if input_text else ""
        )

        prompt = f"""{context_section}Given this Perspective:

<perspective>
{pp_context}
</perspective>

Generate apex statements for both transformation paths within the specified sweet spots:

1. **Re+ apex** (A- → T+ reflection path):
   - A way of thinking/understanding that naturally guides from A's problems toward T's benefits
   - Embodies "affinity with T without instantiating T"
   - MUST use proactiveness in range {RE_PLUS_SWEET_SPOT["proactiveness_min"]} - {RE_PLUS_SWEET_SPOT["proactiveness_max"]}
   - MUST use insight in range {RE_PLUS_SWEET_SPOT["insight_min"]} - {RE_PLUS_SWEET_SPOT["insight_max"]}

2. **Ac+ apex** (T- → A+ action path):
   - A way of acting/behaving that naturally guides from T's problems toward A's benefits
   - Embodies "affinity with A without instantiating A"
   - MUST use proactiveness in range {AC_PLUS_SWEET_SPOT["proactiveness_min"]} - {AC_PLUS_SWEET_SPOT["proactiveness_max"]}
   - MUST use insight in range {AC_PLUS_SWEET_SPOT["insight_min"]} - {AC_PLUS_SWEET_SPOT["insight_max"]}

For each apex, provide:
- A statement (1-15 words)
- The exact insight_label and proactiveness_label from the taxonomy
- An explanation of why this represents the transformation path"""

        return await self._conversation.submit(
            response_model=ApexPairDto,
            user_content=prompt,
        )

    def _to_apex_dto(
        self, candidate: ApexCandidateDto, sweet_spot: dict[str, float]
    ) -> ApexDto:
        """Convert candidate to ApexDto with numeric coordinates, clamped to sweet spot."""
        insight_label = candidate.insight_label.capitalize()
        proactiveness_label = candidate.proactiveness_label.capitalize()

        # Get numeric values from labels
        try:
            insight = insight_label_to_value(insight_label)
        except ValueError:
            # Default to middle of sweet spot if label not recognized
            insight = (sweet_spot["insight_min"] + sweet_spot["insight_max"]) / 2

        try:
            proactiveness = proactiveness_label_to_value(proactiveness_label)
        except ValueError:
            # Default to middle of sweet spot if label not recognized
            proactiveness = (
                sweet_spot["proactiveness_min"] + sweet_spot["proactiveness_max"]
            ) / 2

        # Clamp to sweet spot ranges
        insight = max(
            sweet_spot["insight_min"], min(sweet_spot["insight_max"], insight)
        )
        proactiveness = max(
            sweet_spot["proactiveness_min"],
            min(sweet_spot["proactiveness_max"], proactiveness),
        )

        return ApexDto(
            statement=candidate.statement,
            insight=insight,
            proactiveness=proactiveness,
            insight_label=insight_label,
            proactiveness_label=proactiveness_label,
        )


# Backward compatibility aliases
ApexDerivation = AcReApexDerivation
ApexDerivationResultDto = AcReApexDerivationResultDto
