from typing import (Callable, Dict, Generic, Tuple, TypeVar, Union, overload)

from dialectical_framework.analyst.domain.transition import Transition
from dialectical_framework.analyst.domain.transition_cell_to_cell import \
    TransitionCellToCell
from dialectical_framework.synthesist.domain.dialectical_component import DialecticalComponent
from dialectical_framework.enums.predicate import Predicate
from dialectical_framework.synthesist.domain.wheel_segment import WheelSegment

T = TypeVar("T", bound=Transition)

AliasInput = Union[str, DialecticalComponent, list[Union[str, DialecticalComponent]]]


def _extract_aliases(input_data: AliasInput) -> list[str]:
    """Extract aliases from various input types."""
    if isinstance(input_data, str):
        return [input_data]
    elif isinstance(input_data, DialecticalComponent):
        return [input_data.alias]
    elif isinstance(input_data, list):
        aliases = []
        for item in input_data:
            if isinstance(item, str):
                aliases.append(item)
            elif isinstance(item, DialecticalComponent):
                aliases.append(item.alias)
        return aliases
    else:
        raise TypeError(f"Unsupported input type: {type(input_data)}")


class DirectedGraph(Generic[T]):
    def __init__(self):
        self._transitions: Dict[Tuple[frozenset[str], frozenset[str]], T] = {}

    def add_transition(self, transition: T) -> None:
        """Add a transition to the directed graph."""
        key = (
            frozenset(transition.source_aliases),
            frozenset(transition.target_aliases),
        )

        # For TransitionOneToOne, ensure only one outgoing transition per source
        if isinstance(transition, TransitionCellToCell):
            for existing_key, existing_transition in self._transitions.items():
                if existing_key[0] == key[0]:  # Same source aliases
                    raise ValueError(
                        f"Multiple outgoing transitions for source aliases {transition.source_aliases} found. Only one is allowed."
                    )

        self._transitions[key] = transition

    def get_transition(
        self, source_aliases: AliasInput, target_aliases: AliasInput
    ) -> T | None:
        """Retrieve a transition by source and target aliases."""
        source_aliases_list = _extract_aliases(source_aliases)
        target_aliases_list = _extract_aliases(target_aliases)
        key = (frozenset(source_aliases_list), frozenset(target_aliases_list))
        return self._transitions.get(key)

    def get_transitions_from_source(self, source_aliases: AliasInput) -> list[T]:
        """Get all transitions that have the given source aliases."""
        source_aliases_list = _extract_aliases(source_aliases)
        source_set = frozenset(source_aliases_list)
        return [
            transition
            for (src_set, _), transition in self._transitions.items()
            if src_set == source_set
        ]

    def get_first_transition_from_source(self, source_aliases: AliasInput) -> T | None:
        """Get the first transition that has the given source aliases."""
        transitions = self.get_transitions_from_source(source_aliases)
        return transitions[0] if transitions else None

    def get_all_transitions(self) -> list[T]:
        """
        Get all transitions in the graph. Be mindful that these transitions might not be forming paths.
        So rather consider using the "traverse_dfs_with_paths" or "first_path" method.
        """
        return list(self._transitions.values())

    def get_transition_count(self) -> int:
        """Get the number of transitions in the graph."""
        return len(self._transitions)

    def is_empty(self) -> bool:
        """Check if the graph has no transitions."""
        return len(self._transitions) == 0

    def find_outbound_source_aliases(self, start: WheelSegment) -> list[list[str]]:
        outbound_source_aliases = []
        start_possible_components = {
            comp.alias for comp in [start.t, start.t_plus, start.t_minus] if comp
        }
        for (_, _), transition in self._transitions.items():
            transition_source = transition.source
            if isinstance(transition_source, DialecticalComponent):
                transition_source_components = {transition_source.alias}
            else:  # WheelSegment
                transition_source_components = {
                    comp.alias
                    for comp in [
                        transition_source.t,
                        transition_source.t_plus,
                        transition_source.t_minus,
                    ]
                    if comp
                }

            if start_possible_components.issubset(transition_source_components):
                outbound_source_aliases.append(transition.source_aliases)

        return outbound_source_aliases

    @overload
    def remove_transition(
        self, source_aliases: AliasInput, target_aliases: AliasInput
    ) -> bool:
        """Remove a transition by source and target aliases. Returns True if removed, False if not found."""
        ...

    @overload
    def remove_transition(self, transition: T) -> bool:
        """Remove a transition by Transition object."""
        ...

    def remove_transition(
        self, source_aliases_or_transition, target_aliases=None
    ) -> bool:
        """Remove a transition by source and target aliases or by Transition object."""
        if hasattr(source_aliases_or_transition, "source_aliases") and hasattr(
            source_aliases_or_transition, "target_aliases"
        ):
            # Called with Transition object
            transition = source_aliases_or_transition
            key = (
                frozenset(transition.source_aliases),
                frozenset(transition.target_aliases),
            )
        else:
            # Called with source_aliases and target_aliases
            source_aliases_list = _extract_aliases(source_aliases_or_transition)
            target_aliases_list = _extract_aliases(target_aliases)
            key = (frozenset(source_aliases_list), frozenset(target_aliases_list))

        if key in self._transitions:
            del self._transitions[key]
            return True
        return False

    def clear(self) -> None:
        """Remove all transitions from the graph."""
        self._transitions.clear()

    def traverse_dfs_with_paths(
        self,
        start_aliases: AliasInput | None = None,
        visit_callback: Callable[[list[T], bool], None] | None = None,
        predicate_filter: Predicate | None = None,
    ) -> list[list[T]]:
        """
        Traverse all possible paths in the graph, detecting circles per path.
        Returns all complete paths found.

        Args:
            start_aliases: Starting aliases for traversal
            visit_callback: Optional callback function called for each path
            predicate_filter: If provided, only traverse transitions with this predicate type
        """
        all_paths = []

        def _can_connect_constructively(
            target_aliases: list[str], next_source_aliases: list[str]
        ) -> bool:
            """
            For constructively_converges_to, check if segments can connect at the segment level.
            E.g., [T1-, T1] -> [T2+] can connect to [T2-, T2] -> [T3+] because T2 is shared.
            """
            # Extract base aliases (remove +/- suffixes)
            target_bases = {alias.rstrip("+-") for alias in target_aliases}
            source_bases = {alias.rstrip("+-") for alias in next_source_aliases}

            # Check if there's any overlap at the base level
            return bool(target_bases & source_bases)

        def _find_constructive_transitions(
            current_target_aliases: list[str],
        ) -> list[T]:
            """
            Find all transitions that can constructively connect to the current target.
            """
            constructive_transitions = []
            all_transitions_inner = self.get_all_transitions()

            for transition in all_transitions_inner:
                if (
                    transition.predicate in [Predicate.CONSTRUCTIVELY_CONVERGES_TO, Predicate.TRANSFORMS_TO]
                    and _can_connect_constructively(
                        current_target_aliases, transition.source_aliases
                    )
                ):
                    constructive_transitions.append(transition)

            return constructive_transitions

        def _would_create_constructive_cycle(
            current_aliases: list[str], visited_in_path: set
        ) -> bool:
            """
            For constructively_converges_to, check if current aliases would create a cycle
            by checking segment-level overlap with any visited node.
            """
            current_bases = {alias.rstrip("+-") for alias in current_aliases}

            for visited_key in visited_in_path:
                visited_bases = {alias.rstrip("+-") for alias in visited_key}
                if current_bases & visited_bases:  # If there's any base overlap
                    return True
            return False

        def _dfs_helper(
            current_aliases: list[str],
            current_path: list[T],
            visited_in_path: set,
            current_predicate: str | None = None,
        ):
            current_key = frozenset(current_aliases)

            # Check for cycle based on predicate type
            if current_predicate in [Predicate.CONSTRUCTIVELY_CONVERGES_TO, Predicate.TRANSFORMS_TO]:
                # For constructive convergence, check segment-level overlap
                if _would_create_constructive_cycle(current_aliases, visited_in_path):
                    # Found a cycle in this path - record the path up to this point
                    all_paths.append(current_path.copy())
                    if visit_callback:
                        visit_callback(current_path, True)
                    return
            else:
                # For other predicates, use exact alias matching
                if current_key in visited_in_path:
                    # Found a cycle in this path - record the path up to this point
                    all_paths.append(current_path.copy())
                    if visit_callback:
                        visit_callback(current_path, True)
                    return

            # Add to current path's visited set
            new_visited = visited_in_path | {current_key}

            # Get transitions based on predicate type
            if current_predicate in [Predicate.CONSTRUCTIVELY_CONVERGES_TO, Predicate.TRANSFORMS_TO]:
                # For constructive convergence, find transitions that can connect at segment level
                transitions = _find_constructive_transitions(current_aliases)
            else:
                # Normal case: get transitions from exact source match
                transitions = self.get_transitions_from_source(current_aliases)

            # Filter transitions based on predicate requirements
            if predicate_filter is not None:
                # Only allow transitions with the specified predicate
                transitions = [
                    t for t in transitions if t.predicate == predicate_filter
                ]
            elif current_predicate is not None:
                # If we're already in a path with a specific predicate, only allow same predicate
                transitions = [
                    t for t in transitions if t.predicate == current_predicate
                ]

            if not transitions:
                # End of path - record it
                all_paths.append(current_path.copy())
                if visit_callback:
                    visit_callback(current_path, False)
                return

            # Explore each outgoing edge separately
            for transition in transitions:
                new_path = current_path + [transition]
                target_key = frozenset(transition.target_aliases)

                # Determine the predicate for the next step
                next_predicate = (
                    current_predicate
                    if current_predicate is not None
                    else transition.predicate
                )

                # Check if target would create a cycle based on predicate type
                if next_predicate in [Predicate.CONSTRUCTIVELY_CONVERGES_TO, Predicate.TRANSFORMS_TO]:
                    # For constructive convergence, check segment-level cycle
                    if _would_create_constructive_cycle(
                        transition.target_aliases, new_visited
                    ):
                        # This transition would create a cycle, record the path including this transition
                        all_paths.append(new_path.copy())
                        if visit_callback:
                            visit_callback(new_path, True)
                    else:
                        # Normal case: continue DFS
                        _dfs_helper(
                            transition.target_aliases,
                            new_path,
                            new_visited,
                            next_predicate,
                        )
                else:
                    # For other predicates, use exact matching
                    if target_key in new_visited:
                        # This transition would create a cycle, record the path including this transition
                        all_paths.append(new_path.copy())
                        if visit_callback:
                            visit_callback(new_path, True)
                    else:
                        # Normal case: continue DFS
                        _dfs_helper(
                            transition.target_aliases,
                            new_path,
                            new_visited,
                            next_predicate,
                        )

        if start_aliases is None:
            # Get all transitions and find unique source aliases
            all_transitions = self.get_all_transitions()
            if all_transitions:
                first_transition = all_transitions[0]
                start_aliases_list = first_transition.source_aliases
            else:
                return []
        else:
            start_aliases_list = _extract_aliases(start_aliases)

        _dfs_helper(start_aliases_list, [], set())

        return all_paths

    def first_path(self, start_aliases: AliasInput | None = None) -> list[T]:
        """
        We normally deal with cycles and spirals, so first path is mostly enough.
        """
        # TODO: very inefficient, we shouldn't be traversing the whole graph just to get the first path
        paths = self.traverse_dfs_with_paths(start_aliases)
        return paths[0] if paths else []

    def count_circles(self) -> int:
        """
        Count the number of distinct cycles (circles) in the directed graph.
        Each unique cycle is counted only once, regardless of starting point.

        Returns:
            Number of distinct cycles found in the graph
        """
        if self.is_empty():
            return 0

        detected_cycles = set()

        # Get all unique starting nodes
        all_nodes = set()
        for (src_set, tgt_set), _ in self._transitions.items():
            all_nodes.update(src_set)
            all_nodes.update(tgt_set)

        # Check each node as a potential cycle start
        for start_node in all_nodes:
            paths = self.traverse_dfs_with_paths(start_node)

            for path in paths:
                if path:  # Non-empty path
                    # Check if end connects back to start
                    last_transition = path[-1]
                    path_end = frozenset(last_transition.target_aliases)
                    path_start = frozenset([start_node])

                    if path_end == path_start:
                        # Found a cycle! Extract all nodes in the cycle
                        cycle_nodes = [
                            frozenset([start_node])
                        ]  # Start with the starting node
                        for transition in path:
                            cycle_nodes.append(frozenset(transition.target_aliases))

                        # Remove the duplicate end node (it's the same as start)
                        cycle_nodes = cycle_nodes[:-1]

                        # Normalize: start from lexicographically smallest node
                        min_node = min(cycle_nodes)
                        min_idx = cycle_nodes.index(min_node)
                        normalized_cycle = tuple(
                            cycle_nodes[min_idx:] + cycle_nodes[:min_idx]
                        )

                        detected_cycles.add(normalized_cycle)

        return len(detected_cycles)

    def pretty(self, start_aliases: AliasInput | None = None) -> str:
        paths = self.traverse_dfs_with_paths(start_aliases=start_aliases)
        paths_pieces = []
        for path in paths:
            current_str = None
            for i, transition in enumerate(path):
                if current_str is None:
                    current_str = f"{transition.source_aliases}"
                if i == len(path) - 1 and tuple(transition.target_aliases) == tuple(
                    path[0].source_aliases
                ):
                    # Skip last node if it equals the first node (completing the cycle)
                    continue
                current_str += f" -> {transition.target_aliases}"
            paths_pieces.append(current_str)
        return "\n".join(paths_pieces) if paths_pieces else "<empty>"

    def __str__(self):
        return self.pretty()
