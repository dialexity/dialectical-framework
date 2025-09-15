from typing import List, Tuple, Dict

from tabulate import tabulate

from dialectical_framework import Wheel, Cycle


def dw_report(permutations: List[Wheel] | Wheel) -> str:
    """
    Generate a report of wheel permutations.

    Args:
        permutations: List of wheels or single wheel to report on
    """
    if isinstance(permutations, Wheel):
        permutations = [permutations]

    permutations = permutations.copy()
    permutations.sort(key=lambda w: w.score if w.score is not None else 0, reverse=True)

    grouped: Dict[str, Tuple[Cycle, List[Wheel]]] = {}
    for w in permutations:
        cycle_str = w.t_cycle.cycle_str()
        group_key = cycle_str
        if group_key not in grouped:
            grouped[group_key] = (w.t_cycle, [])
        grouped[group_key][1].append(w)

    report = ""

    for group_key, group in grouped.items():
        t_cycle, grouped_wheel_permutations = group

        # Format scores with labels aligned
        t_cycle_scores = f"S={_fmt_score(t_cycle.score, colorize=True)} | CF={_fmt_score(t_cycle.contextual_fidelity)} | P={_fmt_score(t_cycle.probability)}"
        gr = f"{group_key} [{t_cycle_scores}]\n"

        # Add cycles in this group with aligned scores
        for i, w in enumerate(grouped_wheel_permutations):
            cycle_str = w.cycle.cycle_str() if hasattr(w, 'cycle') and w.cycle else ''
            wheel_scores = f"S={_fmt_score(w.cycle.score, colorize=True)} | CF={_fmt_score(w.cycle.contextual_fidelity)} | P={_fmt_score(w.cycle.probability)}"
            gr += f"  {i}. {cycle_str} [{wheel_scores}]\n"

        # Display detailed wheel information
        for i, w in enumerate(grouped_wheel_permutations):
            if i == 0:
                report += f"\n{gr}\n"
            else:
                report += "\n"

            # Display wheel header with aligned, colorized scores
            wheel_scores = f"S={_fmt_score(w.score, colorize=True)} | CF={_fmt_score(w.contextual_fidelity)} | P={_fmt_score(w.probability)}"
            report += f"Wheel {i} [{wheel_scores}]\n"

            # Display spiral with aligned, colorized scores if available
            if hasattr(w, 'spiral'):
                spiral_scores = f"S={_fmt_score(w.spiral.score, colorize=True)} | CF={_fmt_score(w.spiral.contextual_fidelity)} | P={_fmt_score(w.spiral.probability)}"
                report += f"Spiral [{spiral_scores}]\n"

            # Add tabular display of wheel components
            report += _print_wheel_tabular(w) + "\n"

    return report


def _fmt_score(value, *, colorize: bool = False) -> str:
    """
    Format score values consistently.

    Args:
        value: The score value to format
        colorize: Whether to colorize the score based on value (higher = better)
    """
    if value is None:
        return "None"

    if isinstance(value, (int, float)):
        formatted = f"{value:.3f}"

        if colorize:
            # Simple coloring scheme based on value ranges
            if value >= 0.8:
                return f"\033[92m{formatted}\033[0m"  # Green for high values
            elif value >= 0.5:
                return f"\033[93m{formatted}\033[0m"  # Yellow for medium values
            else:
                return f"\033[91m{formatted}\033[0m"  # Red for low values
        return formatted

    return str(value)

def _print_wheel_tabular(self) -> str:
    roles = [
        ("t_minus", "T-"),
        ("t", "T"),
        ("t_plus", "T+"),
        ("a_plus", "A+"),
        ("a", "A"),
        ("a_minus", "A-"),
    ]

    n_units = len(self._wisdom_units)

    # Create headers: WU1_alias, WU1_statement, (transition1), WU2_alias, ...
    headers = []
    for i in range(n_units):
        headers.extend([f"Alias (WU{i + 1})", f"Statement (WU{i + 1})"])

    table = []
    # Build the table: alternate wisdom unit cells and transitions
    for role_attr, role_label in roles:
        row = []
        for i, wu in enumerate(self._wisdom_units):
            # Wisdom unit columns
            component = getattr(wu, role_attr, None)
            row.append(component.alias if component else "")
            row.append(component.statement if component else "")
        table.append(row)

    return tabulate(
        table,
        # headers=headers,
        tablefmt="plain",
    )