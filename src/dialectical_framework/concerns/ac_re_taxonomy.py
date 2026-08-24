"""
Ac-Re Taxonomy constants for Transformation generation.

This module contains the scales, polar pairs, and apex target coordinates
for the Action-Reflection dialectical structure.
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

# Named bands over INSIGHT_SCALE. `ActionExtraction` generates one Ac+ candidate
# per category, so this dict sets the per-edge Transformation count — a wheel
# carries 2N edges × len(INSIGHT_CATEGORIES) Transformations. It lives beside
# INSIGHT_SCALE (rather than in the concern that prompts with it) because the
# two must agree: _LEVEL_TO_CATEGORY below checks that at import time.
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


def _build_level_to_category() -> dict[str, str]:
    """Invert INSIGHT_CATEGORIES into level → category, checking both agree.

    Raises at import time if a category names a level absent from INSIGHT_SCALE,
    or if a scale level belongs to no category. Either would leave the two
    constants silently out of step, and an unmapped level makes a Transformation
    uncategorisable — which in turn makes resume unable to tell what an edge
    already carries.
    """
    mapping: dict[str, str] = {}
    for category, info in INSIGHT_CATEGORIES.items():
        for level in info["levels"]:
            key = level.capitalize()
            if key not in INSIGHT_SCALE:
                raise ValueError(
                    f"INSIGHT_CATEGORIES['{category}'] names level '{level}', "
                    f"which is not in INSIGHT_SCALE"
                )
            mapping[key] = category
    unmapped = set(INSIGHT_SCALE) - set(mapping)
    if unmapped:
        raise ValueError(
            f"INSIGHT_SCALE levels belong to no insight category: "
            f"{sorted(unmapped)}"
        )
    return mapping


_LEVEL_TO_CATEGORY = _build_level_to_category()


def insight_label_to_value(label: str) -> float:
    """Convert insight label to numeric value."""
    key = label.capitalize()
    if key not in INSIGHT_SCALE:
        raise ValueError(
            f"Unknown insight label: {label}. Valid: {list(INSIGHT_SCALE.keys())}"
        )
    return INSIGHT_SCALE[key]


def insight_category_of_label(label: str) -> str:
    """Convert an insight level label to its category ("Leverage" → "Generative")."""
    key = label.capitalize()
    if key not in _LEVEL_TO_CATEGORY:
        raise ValueError(
            f"Unknown insight label: {label}. Valid: {list(_LEVEL_TO_CATEGORY.keys())}"
        )
    return _LEVEL_TO_CATEGORY[key]


def insight_category_of_value(value: float) -> str:
    """Convert a stored insight value to its category (0.6 → "Generative").

    Values written by `insight_label_to_value` land exactly on a scale point,
    but a value round-tripped through the DB may be off by a float epsilon, so
    this snaps to the nearest level rather than comparing bounds. A value
    exactly between two levels resolves to the LOWER one — insight depth is
    not claimed beyond what was measured.

    The distance is ROUNDED before comparing, and that is load-bearing: the
    scale steps by 0.1, so `abs(0.6 - 0.55)` and `abs(0.5 - 0.55)` differ in
    the 17th decimal in binary floating point. Comparing them raw let 0.55
    resolve UP to Leverage/Generative — the tie-break below never fired, and
    the one half-step that crosses a category boundary upward was exactly the
    one this rule exists to catch.
    """
    nearest, _ = min(
        INSIGHT_SCALE.items(),
        key=lambda kv: (round(abs(kv[1] - value), 6), kv[1]),
    )
    return _LEVEL_TO_CATEGORY[nearest]


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
