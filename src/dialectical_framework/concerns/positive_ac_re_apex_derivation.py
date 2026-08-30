"""
AcReApexDerivation: Concern for deriving Re+ and Ac+ apex statements for a wheel edge.

The apex statements represent the reference transformation paths for this specific
edge context, against which other transformations are measured (via HS).

Apexes are generated within sweet-spot coordinate ranges derived from the
taxonomy apex targets (RE_PLUS_APEX_TARGET / AC_PLUS_APEX_TARGET) ± SWEET_SPOT_MARGIN.
See RE_PLUS_SWEET_SPOT / AC_PLUS_SWEET_SPOT for the resolved bounds.

Usage:
    service = AcReApexDerivation()
    apexes = await service.resolve(edge, input_text)
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
from dialectical_framework.concerns.scoring_scales import ASPECT_DEFINITIONS
from dialectical_framework.utils.edge_context import build_edge_context
from dialectical_framework.protocols.has_config import SettingsAware

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.transition import Transition


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

A Perspective is built around a Polarity (T, A) and adds four Aspects (T+, T-, A+, A-).

The two poles:
- T (Thesis): a neutral statement of one side
- A (Antithesis): the opposing side

{ASPECT_DEFINITIONS}

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

1. Each apex should be concise and actionable, longer than a headline
2. They should be complementary (Re+ and Ac+ work together)
3. They should NOT simply restate T+/A+ but describe the PATH to them
4. They should be generative (enabling discovery) not prescriptive
5. Choose labels that fall WITHIN the sweet spot ranges specified above

## Validation

Ac+/Re+ must: (1) not restate A+/T+, (2) be generative, (3) be valid BEFORE A+/T+ are affordable — the operation must work while the constructive aspects are still out of reach, since it is the path that makes them affordable, (4) explain subtlety/non-force, (5) generalize beyond T/A.
"""


class ApexPairDto(BaseModel):
    """Both Re+ and Ac+ apex candidates.

    FLAT ON PURPOSE. This was two nested `ApexCandidateDto` objects and a real
    provider answered with `re_plus_apex` complete and `ac_plus_apex` absent
    (`probe_explore_cost.py`, 2026-08-29) — the SECOND half of the pair, exactly
    as `SynthesisPairDto` dropped `s_minus`. Two observations of one shape: given
    two identically shaped sub-objects, the model finishes the first and treats
    the pattern as satisfied. A missing required field is also the one thing
    `_salvage_envelope` must not repair, so it costs a full re-ask of an already
    expensive call.

    Eight independently named keys cannot be half-satisfied the same way — an
    answer that stops after Re+ leaves four named keys visibly missing.

    `*_explanation` is never read (`_to_apex_dto` uses statement + both labels).
    It stays required because asking for the reasoning is what keeps the labels
    honest, not because anything downstream consumes it.
    """

    re_plus_statement: str = Field(
        description=f"Re+ apex statement: A- → T+ reflection path, concise but longer "
        f"than a headline "
        f"(proactiveness {RE_PLUS_SWEET_SPOT['proactiveness_min']}-{RE_PLUS_SWEET_SPOT['proactiveness_max']}, "
        f"insight {RE_PLUS_SWEET_SPOT['insight_min']}-{RE_PLUS_SWEET_SPOT['insight_max']})"
    )
    re_plus_insight_label: str = Field(
        description="Re+ insight label from taxonomy (e.g., leverage, composition, anticipation)"
    )
    re_plus_proactiveness_label: str = Field(
        description="Re+ proactiveness label from taxonomy (e.g., interpretation, intervention)"
    )
    re_plus_explanation: str = Field(
        description="Why the Re+ statement represents the reflection path and fits its sweet spot"
    )
    ac_plus_statement: str = Field(
        description=f"Ac+ apex statement: T- → A+ action path, concise but longer "
        f"than a headline "
        f"(proactiveness {AC_PLUS_SWEET_SPOT['proactiveness_min']}-{AC_PLUS_SWEET_SPOT['proactiveness_max']}, "
        f"insight {AC_PLUS_SWEET_SPOT['insight_min']}-{AC_PLUS_SWEET_SPOT['insight_max']})"
    )
    ac_plus_insight_label: str = Field(
        description="Ac+ insight label from taxonomy (e.g., leverage, composition, anticipation)"
    )
    ac_plus_proactiveness_label: str = Field(
        description="Ac+ proactiveness label from taxonomy (e.g., interpretation, intervention)"
    )
    ac_plus_explanation: str = Field(
        description="Why the Ac+ statement represents the action path and fits its sweet spot"
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
    Concern for deriving Re+ and Ac+ apex statements for a wheel edge context.

    The derived apexes serve as reference points for calculating Heuristic Similarity (HS)
    of other transformation candidates. Apexes are constrained to sweet spot ranges.
    """

    def __init__(self) -> None:
        self._conversation = ConversationFacilitator()

    async def resolve(
        self,
        edge: Transition,
        input_text: str = "",
    ) -> AcReApexDerivationResultDto:
        """
        Derive Re+ and Ac+ apex statements for a wheel edge.

        The edge's source segment becomes the T-side context and
        the edge's target segment becomes the A-side context.

        Args:
            edge: The wheel edge (Transition between main statements)
            input_text: Optional source content context

        Returns:
            AcReApexDerivationResultDto with Re+ and Ac+ apexes including coordinates
        """

        source_segment = edge.get_source_wheel_segment()
        target_segment = edge.get_target_wheel_segment()
        if not source_segment or not target_segment:
            raise ValueError(f"Cannot resolve segments for edge {edge.short_hash}")

        if not source_segment.is_complete() or not target_segment.is_complete():
            raise ValueError("Both segments must be complete to derive apexes")

        self._conversation.set_system_prompt(SYSTEM_PROMPT)

        context = build_edge_context(source_segment, target_segment)

        apex_pair = await self._generate_apex_pair(context, input_text)

        re_plus_apex = self._to_apex_dto(
            apex_pair.re_plus_statement,
            apex_pair.re_plus_insight_label,
            apex_pair.re_plus_proactiveness_label,
            RE_PLUS_SWEET_SPOT,
        )
        ac_plus_apex = self._to_apex_dto(
            apex_pair.ac_plus_statement,
            apex_pair.ac_plus_insight_label,
            apex_pair.ac_plus_proactiveness_label,
            AC_PLUS_SWEET_SPOT,
        )

        result = AcReApexDerivationResultDto(
            re_plus_apex=re_plus_apex,
            ac_plus_apex=ac_plus_apex,
        )

        self._report.artifacts["edge_hash"] = edge.short_hash
        self._report.artifacts["re_plus_apex"] = re_plus_apex.model_dump()
        self._report.artifacts["ac_plus_apex"] = ac_plus_apex.model_dump()
        self._report.summary = (
            f"Derived apexes for edge {edge.short_hash}: "
            f"Re+ ({re_plus_apex.proactiveness:.1f}, {re_plus_apex.insight:.1f}), "
            f"Ac+ ({ac_plus_apex.proactiveness:.1f}, {ac_plus_apex.insight:.1f})"
        )

        return result

    async def _generate_apex_pair(
        self,
        edge_context: str,
        input_text: str,
    ) -> ApexPairDto:
        """Generate Re+ and Ac+ apex candidates."""
        context_section = (
            f"<context>\n{input_text}\n</context>\n\n" if input_text else ""
        )

        prompt = f"""{context_section}Given this Perspective:

<perspective>
{edge_context}
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

For EACH of the two apexes, provide:
- A statement (up to {self.settings.transition_length} words)
- The exact insight_label and proactiveness_label from the taxonomy
- An explanation of why this represents the transformation path

Both apexes are required. Re+ and Ac+ are the two halves of one circular
causality — an answer carrying only one describes half a loop, and the loop is
the whole point."""

        return await self._conversation.submit(
            response_model=ApexPairDto,
            user_content=prompt,
        )

    def _to_apex_dto(
        self,
        statement: str,
        raw_insight_label: str,
        raw_proactiveness_label: str,
        sweet_spot: dict[str, float],
    ) -> ApexDto:
        """Convert one side of the pair to ApexDto, clamped to its sweet spot."""
        insight_label = raw_insight_label.capitalize()
        proactiveness_label = raw_proactiveness_label.capitalize()

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
            statement=statement,
            insight=insight,
            proactiveness=proactiveness,
            insight_label=insight_label,
            proactiveness_label=proactiveness_label,
        )


# Backward compatibility aliases
ApexDerivation = AcReApexDerivation
ApexDerivationResultDto = AcReApexDerivationResultDto
