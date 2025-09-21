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
        t_cycle_scores = f"S={_fmt_score(t_cycle.score, colorize=True)} | R={_fmt_p_or_r(t_cycle, 'relevance', colorize=True)} | P={_fmt_p_or_r(t_cycle, 'probability', colorize=True)}"
        gr = f"{group_key} [{t_cycle_scores}]\n"

        # Add cycles in this group with aligned scores
        for i, w in enumerate(grouped_wheel_permutations):
            cycle_str = w.cycle.cycle_str() if hasattr(w, 'cycle') and w.cycle else ''
            wheel_scores = f"S={_fmt_score(w.cycle.score, colorize=True)} | R={_fmt_p_or_r(w.cycle, 'relevance', colorize=True)} | P={_fmt_p_or_r(w.cycle, 'probability', colorize=True)}"
            gr += f"  {i}. {cycle_str} [{wheel_scores}]\n"

        # Display detailed wheel information
        for i, w in enumerate(grouped_wheel_permutations):
            if i == 0:
                report += f"\n{gr}\n"
            else:
                report += "\n"

            # Display wheel header with aligned, colorized scores
            wheel_scores = f"S={_fmt_score(w.score, colorize=True)} | R={_fmt_p_or_r(w, 'relevance', colorize=True)} | P={_fmt_p_or_r(w, 'probability', colorize=True)}"
            report += f"Wheel {i} [{wheel_scores}]\n"

            # Display spiral with aligned, colorized scores if available
            spiral_scores = f"S={_fmt_score(w.spiral.score, colorize=True)} | R={_fmt_p_or_r(w.spiral, 'relevance', colorize=True)} | P={_fmt_p_or_r(w.spiral, 'probability', colorize=True)}"
            report += f"Spiral [{spiral_scores}]\n"

            # Display wisdom unit transformations with scores
            for wu_idx, wu in enumerate(w.wisdom_units):
                if wu.transformation:
                    transformation_scores = f"S={_fmt_score(wu.transformation.score, colorize=True)} | R={_fmt_p_or_r(wu.transformation, 'relevance', colorize=True)} | P={_fmt_p_or_r(wu.transformation, 'probability', colorize=True)}"
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

def _fmt_p_or_r(obj, prop_name, *, colorize: bool = False) -> str:
    """
    Format a property, showing it in brackets if it comes from calculated fields.

    Args:
        obj: The object containing the property
        prop_name: The property name ('relevance' or 'probability')
        colorize: Whether to apply color formatting
    """
    # Get the property value
    value = getattr(obj, prop_name, None)
    if value is None:
        return "None"

    formatted = _fmt_score(value, colorize=colorize)

    # For Ratable objects, check if manual value is None (meaning we're using calculated)
    manual_field = f"manual_{prop_name}"
    if hasattr(obj, manual_field):
        manual_value = getattr(obj, manual_field)
        is_calculated = manual_value is None
    else:
        # For pure Assessable objects, all values come from calculated fields
        is_calculated = True

    # Show in brackets if calculated
    if is_calculated:
        return f"[{formatted}]"
    else:
        return formatted

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
    score_info = f"S={_fmt_score(rationale.score)} | R={_fmt_p_or_r(rationale, 'relevance')} | P={_fmt_p_or_r(rationale, 'probability')}"

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
            r = _fmt_p_or_r(transition, 'relevance', colorize=True)
            p = _fmt_p_or_r(transition, 'probability', colorize=True)

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
                r,
                p,
                rationales_tree
            ])

    # If no transitions found, return empty string
    if not transitions_data:
        return ""

    # Create transitions table
    headers = ["Cycle", "Transition", "Score", "R", "P", "Rationales"]
    return "Transitions:\n" + tabulate(transitions_data, headers=headers, tablefmt="grid")