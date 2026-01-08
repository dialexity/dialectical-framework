"""
Score formatting utilities for displaying S/R/P values.

Provides consistent formatting for scores with:
- Colorization (green/yellow/red based on value)
- Brackets for calculated values vs plain for manual values
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity


def fmt_score(value: Optional[float], *, colorize: bool = False) -> str:
    """
    Format a score value consistently.

    Args:
        value: The score value to format (0.0-1.0 or None)
        colorize: Whether to colorize based on value (higher = better)

    Returns:
        Formatted string like "0.750" or "None"

    Example:
        >>> fmt_score(0.85, colorize=True)
        '\x1b[92m0.850\x1b[0m'  # Green
    """
    if value is None:
        return "None"

    formatted = f"{value:.3f}"

    if colorize:
        if value >= 0.8:
            return f"\033[92m{formatted}\033[0m"  # Green for high values
        elif value >= 0.5:
            return f"\033[93m{formatted}\033[0m"  # Yellow for medium values
        else:
            return f"\033[91m{formatted}\033[0m"  # Red for low values

    return formatted


def fmt_probability(
    entity: AssessableEntity,
    *,
    colorize: bool = False
) -> str:
    """
    Format probability showing [brackets] if calculated.

    Args:
        entity: The assessable entity to get probability from
        colorize: Whether to colorize based on value

    Returns:
        "0.750" for manual, "[0.750]" for calculated, "None" if missing

    Example:
        >>> fmt_probability(component, colorize=True)
        '[0.850]'  # Calculated value in brackets
    """
    value = entity.probability
    formatted = fmt_score(value, colorize=colorize)

    if value is not None and entity.is_probability_calculated:
        return f"[{formatted}]"
    return formatted


def fmt_relevance(
    entity: AssessableEntity,
    *,
    colorize: bool = False
) -> str:
    """
    Format relevance showing [brackets] if calculated.

    Args:
        entity: The assessable entity to get relevance from
        colorize: Whether to colorize based on value

    Returns:
        "0.750" for manual, "[0.750]" for calculated, "None" if missing

    Example:
        >>> fmt_relevance(component, colorize=True)
        '0.900'  # Manual value without brackets
    """
    value = entity.relevance
    formatted = fmt_score(value, colorize=colorize)

    if value is not None and entity.is_relevance_calculated:
        return f"[{formatted}]"
    return formatted


def fmt_scores(
    entity: AssessableEntity,
    *,
    colorize: bool = False
) -> str:
    """
    Format all scores (S, R, P) for an entity in one line.

    Args:
        entity: The assessable entity
        colorize: Whether to colorize based on values

    Returns:
        String like "S=0.750 | R=[0.850] | P=0.900"

    Example:
        >>> fmt_scores(wheel, colorize=True)
        'S=0.750 | R=[0.850] | P=0.900'
    """
    s = fmt_score(entity.score, colorize=colorize)
    r = fmt_relevance(entity, colorize=colorize)
    p = fmt_probability(entity, colorize=colorize)

    return f"S={s} | R={r} | P={p}"
