"""
Ac-Re Taxonomy constants for Transformation generation.

This module contains the scales, polar pairs, and apex target coordinates
for the Action-Reflection dialectical structure.

See docs/r&d/ac_re-taxonomy.md for full specification.
"""

from __future__ import annotations

# Y-Axis: Insight Scale (0.0 → 1.0)
# Measures the depth of understanding/transformation in a transition
INSIGHT_SCALE = {
    # APEX / GENERATIVE / Transformational
    "Transcendence": 1.0,  # Paradigm shift, new dimension
    "Redirection": 0.9,  # Fundamental change of direction
    "Inversion": 0.8,  # Flipping perspective entirely
    # GENERATIVE / Strategic
    "Anticipation": 0.7,  # Acting/thinking ahead of events
    "Leverage": 0.6,  # Finding and using leverage points (APEX Y)
    # CONFIGURATIONAL
    "Composition": 0.5,  # Combining elements in new ways
    "Reformulation": 0.4,  # Restating/restructuring approach
    # CORRECTIVE / Adjusted
    "Variation": 0.3,  # Making deliberate small changes
    "Tuning": 0.2,  # Fine-tuning existing approach
    # CORRECTIVE / Reactive
    "Procedure": 0.1,  # Following established protocol
    "Reflex": 0.0,  # Automatic, instinctive response
}

# X-Axis: Proactiveness Scale (0.0 → 1.0)
# Reflections (Re) occupy 0.0-0.4, Actions (Ac) occupy 0.5-1.0
PROACTIVENESS_SCALE = {
    # Reflections (Re+ = A- → T+, Re- = A+ → T-) — Apex zone: ~0.25
    "Observation": 0.0,  # Passive noticing without judgment
    "Detection": 0.1,  # Identifying patterns or anomalies
    "Interpretation": 0.2,  # Making sense of what's detected (APEX Re)
    "Framing": 0.3,  # Placing in broader context
    "Evaluation": 0.4,  # Assessing value/significance (MIDPOINT)
    # Actions (Ac+ = T- → A+, Ac- = T+ → A-) — Apex zone: ~0.65
    "Coordination": 0.5,  # Aligning multiple elements
    "Intervention": 0.6,  # Stepping in to change something (APEX Ac)
    "Implementation": 0.7,  # Executing a defined plan
    "Configuration": 0.8,  # Arranging/structuring elements
    "Governance": 0.9,  # Directing, setting rules/policies
    "Stewardship": 1.0,  # Active long-term caretaking
}

# Ac → Re Polar Pairs (maps Action to complementary Reflection)
POLAR_PAIRS = {
    "Coordination": "Framing",  # 0.5 → 0.3
    "Intervention": "Interpretation",  # 0.6 → 0.2 (APEX PAIR)
    "Implementation": "Detection",  # 0.7 → 0.1
    "Configuration": "Observation",  # 0.8 → 0.0
    "Governance": "Evaluation",  # 0.9 → 0.4
    "Stewardship": "Evaluation",  # 1.0 → 0.4
}

# Target coordinates for apex derivation
# These are the "ideal" coordinates for Re+ and Ac+ apexes
AC_PLUS_APEX_TARGET = {
    "proactiveness": 0.65,
    "insight": 0.6,
}  # Intervention zone + Leverage
RE_PLUS_APEX_TARGET = {
    "proactiveness": 0.25,
    "insight": 0.6,
}  # Interpretation zone + Leverage

# Reflection labels (Re zone: 0.0-0.4)
REFLECTION_LABELS = [
    "Observation",
    "Detection",
    "Interpretation",
    "Framing",
    "Evaluation",
]

# Action labels (Ac zone: 0.5-1.0)
ACTION_LABELS = [
    "Coordination",
    "Intervention",
    "Implementation",
    "Configuration",
    "Governance",
    "Stewardship",
]


def insight_label_to_value(label: str) -> float:
    """Convert insight label to numeric value."""
    key = label.capitalize()
    if key not in INSIGHT_SCALE:
        raise ValueError(
            f"Unknown insight label: {label}. Valid: {list(INSIGHT_SCALE.keys())}"
        )
    return INSIGHT_SCALE[key]


def proactiveness_label_to_value(label: str) -> float:
    """Convert proactiveness label to numeric value."""
    key = label.capitalize()
    if key not in PROACTIVENESS_SCALE:
        raise ValueError(
            f"Unknown proactiveness label: {label}. Valid: {list(PROACTIVENESS_SCALE.keys())}"
        )
    return PROACTIVENESS_SCALE[key]


def get_polar_pair(label: str) -> str:
    """
    Get the Re+ category for a given Ac+ label.

    Args:
        label: An Action category label (Ac+)

    Returns:
        The complementary Reflection category label (Re+)

    Raises:
        ValueError: If label is not a valid Action category
    """
    key = label.capitalize()
    if key in POLAR_PAIRS:
        return POLAR_PAIRS[key]
    raise ValueError(
        f"Label '{label}' has no polar pair. "
        f"Valid Ac labels: {list(POLAR_PAIRS.keys())}"
    )


def is_reflection_category(label: str) -> bool:
    """Check if a proactiveness label is in the Reflection (Re) zone.

    Not enforced at persistence time — the generation prompts constrain zone
    assignment and LLMs follow reliably. Adding runtime validation would
    complicate the generation pipeline for negligible gain.
    """
    return label.capitalize() in REFLECTION_LABELS


def is_action_category(label: str) -> bool:
    """Check if a proactiveness label is in the Action (Ac) zone.

    See is_reflection_category for rationale on why this isn't enforced at runtime.
    """
    return label.capitalize() in ACTION_LABELS
