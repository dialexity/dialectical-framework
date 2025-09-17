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
        t_cycle_scores = f"S={_fmt_score(t_cycle.score, colorize=True)} | CF={_fmt_cf_or_p(t_cycle, 'contextual_fidelity')} | P={_fmt_cf_or_p(t_cycle, 'probability')}"
        gr = f"{group_key} [{t_cycle_scores}]\n"

        # Add cycles in this group with aligned scores
        for i, w in enumerate(grouped_wheel_permutations):
            cycle_str = w.cycle.cycle_str() if hasattr(w, 'cycle') and w.cycle else ''
            wheel_scores = f"S={_fmt_score(w.cycle.score, colorize=True)} | CF={_fmt_cf_or_p(w.cycle, 'contextual_fidelity')} | P={_fmt_cf_or_p(w.cycle, 'probability')}"
            gr += f"  {i}. {cycle_str} [{wheel_scores}]\n"

        # Display detailed wheel information
        for i, w in enumerate(grouped_wheel_permutations):
            if i == 0:
                report += f"\n{gr}\n"
            else:
                report += "\n"

            # Display wheel header with aligned, colorized scores
            wheel_scores = f"S={_fmt_score(w.score, colorize=True)} | CF={_fmt_cf_or_p(w, 'contextual_fidelity')} | P={_fmt_cf_or_p(w, 'probability')}"
            report += f"Wheel {i} [{wheel_scores}]\n"

            # Display spiral with aligned, colorized scores if available
            spiral_scores = f"S={_fmt_score(w.spiral.score, colorize=True)} | CF={_fmt_cf_or_p(w.spiral, 'contextual_fidelity')} | P={_fmt_cf_or_p(w.spiral, 'probability')}"
            report += f"Spiral [{spiral_scores}]\n"

            # Display wisdom unit transformations with scores
            for wu_idx, wu in enumerate(w.wisdom_units):
                if wu.transformation:
                    transformation_scores = f"S={_fmt_score(wu.transformation.score, colorize=True)} | CF={_fmt_cf_or_p(wu.transformation, 'contextual_fidelity')} | P={_fmt_cf_or_p(wu.transformation, 'probability')}"
                    report += f"WU{wu_idx+1} Transformation [{transformation_scores}]\n"
                else:
                    report += f"WU{wu_idx+1} Transformation [None]\n"

            # Add tabular display of wheel components and transitions
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

def _fmt_cf_or_p(obj, attr_name: str, *, colorize: bool = False) -> str:
    """
    Format CF or P values, using calculated values when manual is None.
    Calculated values are shown in brackets to distinguish from manual values.

    Args:
        obj: Object with the attribute and calculation method
        attr_name: 'contextual_fidelity' or 'probability'
        colorize: Whether to colorize the score
    """
    manual_value = getattr(obj, attr_name, None)

    if manual_value is not None:
        # Manual value exists, format normally
        return _fmt_score(manual_value, colorize=colorize)

    # Manual value is None, try to calculate
    calc_method_name = f"calculate_{attr_name}"
    if hasattr(obj, calc_method_name):
        calculated_value = getattr(obj, calc_method_name)()
        if calculated_value is not None:
            # Format calculated value in brackets
            formatted = _fmt_score(calculated_value, colorize=colorize)
            return f"[{formatted}]"

    # No manual or calculated value
    return "None"

def _print_wheel_tabular(wheel) -> str:
    roles = [
        ("t_minus", "T-"),
        ("t", "T"),
        ("t_plus", "T+"),
        ("a_plus", "A+"),
        ("a", "A"),
        ("a_minus", "A-"),
    ]

    # Try to access wisdom units through public interface if available
    wisdom_units = wheel.wisdom_units
    n_units = len(wisdom_units)

    # Create headers: WU1_alias, WU1_statement, (transition1), WU2_alias, ...
    headers = []
    for i in range(n_units):
        headers.extend([f"Alias (WU{i + 1})", f"Statement (WU{i + 1})"])

    table = []
    # Build the table: alternate wisdom unit cells and transitions
    for role_attr, role_label in roles:
        row = []
        for i, wu in enumerate(wisdom_units):
            # Wisdom unit columns
            component = getattr(wu, role_attr, None)
            row.append(component.alias if component else "")
            row.append(component.statement if component else "")
        table.append(row)

    component_table = tabulate(
        table,
        tablefmt="plain",
    )

    # Add transition information table
    transitions_table = _print_transitions_table(wheel)

    return component_table + "\n\n" + transitions_table if transitions_table else component_table

def _format_rationale_tree(rationale, indent=0):
    """Format a rationale and its child rationales as a tree structure."""
    if not rationale:
        return ""

    # Format this rationale with score information
    headline = rationale.headline or "Unnamed rationale"
    score_info = f"S={_fmt_score(rationale.score)} | CF={_fmt_cf_or_p(rationale, 'contextual_fidelity')} | P={_fmt_cf_or_p(rationale, 'probability')}"

    # Build the tree line with proper indentation
    tree_line = "  " * indent + "- " + headline + f" [{score_info}]"

    # Add child rationales recursively
    child_lines = ""
    for child in rationale.rationales:
        child_lines += "\n" + _format_rationale_tree(child, indent + 1)

    return tree_line + child_lines

def _print_transitions_table(wheel) -> str:
    """Print a table of all transitions with their scores, CF, and P values."""

    # Get cycles to extract transitions
    cycles = [
        ('T-cycle', wheel.t_cycle),
        ('TA-cycle', wheel.cycle),
        ('Spiral', wheel.spiral)
    ]

    # Add wisdom unit transformations
    for wu_idx, wu in enumerate(wheel.wisdom_units):
        if wu.transformation:
            cycles.append((f'WU{wu_idx+1} Transformation', wu.transformation))

    # If we don't have any cycles with transitions, return empty string
    if not cycles:
        return ""

    transitions_data = []

    # Extract transitions from each cycle
    for cycle_name, cycle in cycles:
        transitions = cycle.graph.get_all_transitions()
        for transition in transitions:
            # Format source and target nicely
            source = ', '.join(transition.source_aliases)
            target = ', '.join(transition.target_aliases)

            # Format transition representation
            trans_repr = f"{source} → {target}"

            # Get scores
            score = _fmt_score(transition.score, colorize=True)
            cf = _fmt_cf_or_p(transition, 'contextual_fidelity')
            p = _fmt_cf_or_p(transition, 'probability')

            # Format rationales tree
            rationales_tree = ""
            for rationale in transition.rationales:
                rationales_tree += _format_rationale_tree(rationale) + "\n"

            if not rationales_tree:
                rationales_tree = "No rationales"

            # Add to data
            transitions_data.append([
                cycle_name,
                trans_repr,
                score,
                cf,
                p,
                rationales_tree
            ])

    # If no transitions found, return empty string
    if not transitions_data:
        return ""

    # Create transitions table
    headers = ["Cycle", "Transition", "Score", "CF", "P", "Rationales"]
    return "Transitions:\n" + tabulate(transitions_data, headers=headers, tablefmt="grid")