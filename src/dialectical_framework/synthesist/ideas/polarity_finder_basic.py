from __future__ import annotations

from typing import TYPE_CHECKING, Union

from dependency_injector.wiring import Provide, inject

from dialectical_framework.enums.di import DI
from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
from dialectical_framework.graph.nodes.ideas import Ideas
from dialectical_framework.graph.nodes.input import Input
from dialectical_framework.protocols.input_resolver import InputResolver
from dialectical_framework.protocols.polarity_finder import PolarityFinder

if TYPE_CHECKING:
    from dialectical_framework.protocols.thesis_extractor import ThesisExtractor
    from dialectical_framework.protocols.antithesis_extractor import AntithesisExtractor


# Type alias for given parameter items
GivenItem = Union[str, DialecticalComponent, None]
GivenTuple = tuple[GivenItem, GivenItem]


class PolarityFinderBasic(PolarityFinder):
    """
    SOA-ready polarity finder service.

    Orchestrates polarity extraction by coordinating thesis and antithesis extractors.
    Creates graph nodes and OPPOSITE_OF relationships between thesis-antithesis pairs.

    This class handles:
    - Input normalization (strings, graph nodes, lists, tuples)
    - Selective generation (via `at` parameter)
    - Deduplication across the matrix
    - Graph node creation and relationship management
    """

    @inject
    def __init__(
        self,
        input_resolver: InputResolver = Provide[DI.input_resolver],
        thesis_extractor: ThesisExtractor = Provide[DI.thesis_extractor],
        antithesis_extractor: AntithesisExtractor = Provide[DI.antithesis_extractor],
    ):
        self._input_resolver = input_resolver
        self._thesis_extractor = thesis_extractor
        self._antithesis_extractor = antithesis_extractor

    def _get_statement(self, item: GivenItem) -> str | None:
        """Extract statement string from item (graph node, string, or None).

        Returns None for empty strings (treated as missing).
        """
        if item is None:
            return None
        if isinstance(item, DialecticalComponent):
            return item.statement or None  # Treat "" as None
        return item or None  # Treat "" as None

    def _has_content(self, item: GivenItem) -> bool:
        """Check if item has meaningful content (non-empty statement)."""
        return bool(self._get_statement(item))

    async def extract_polarities(
        self,
        *,
        source: Union[Input, Ideas],
        given: Union[
            str,
            list[GivenItem],
            list[GivenTuple],
        ] = None,
        at: None | int | list[int] = None,
        not_like_these: list[str] | None = None,
    ) -> list[tuple[DialecticalComponent, DialecticalComponent]]:
        """
        Extract polarities and create graph nodes with OPPOSITE_OF relationships.

        Implementation Notes
        -------------------
        1. **Two-phase generation:** First generates missing theses for `(None, None)`
           entries, then generates missing antitheses/opposites in batch.

        2. **Graph node creation:** All extracted components are created as graph nodes
           and connected to source.statements.

        3. **OPPOSITE_OF relationship:** Created between each thesis-antithesis pair.

        4. **Reuse existing nodes:** If given contains DialecticalComponent graph nodes,
           they are reused (not recreated) and connected to source if not already.
        """
        if not given or len(given) == 0:
            given = None

        count = len(given) if isinstance(given, list) else 1
        if count > 4 or count < 1:
            raise ValueError(
                f"Incorrect number of polarities requested. Max 4 are supported."
            )

        # Pre-compute connected identities for O(1) lookup (avoid O(n) query per component)
        connected_ids: set[str] = {comp.hash for comp, _ in source.statements.all()}

        # Normalize given parameter into tuples
        normalized: list[GivenTuple]
        if given is None:
            normalized = [(None, None)]
        elif isinstance(given, str):
            normalized = [(given, None)]
        else:
            if not isinstance(given[0], tuple):
                normalized = [(t, None) for t in given]
            else:
                normalized = given

        # Normalize 'at' parameter into a list of indices
        indices_to_generate: list[int] | None = None
        if at is not None:
            if isinstance(at, int):
                indices_to_generate = [at]
            else:
                indices_to_generate = at

            # Validate indices are within bounds
            for idx in indices_to_generate:
                if idx < 0 or idx >= len(normalized):
                    raise IndexError(
                        f"Index {idx} is out of bounds for given list of length {len(normalized)}"
                    )

        # Collect all provided statements to avoid duplicates (use set for deduplication)
        exclusions: set[str] = set(not_like_these) if not_like_these else set()
        for thesis, antithesis in normalized:
            stmt = self._get_statement(thesis)
            if stmt:
                exclusions.add(stmt)
            stmt = self._get_statement(antithesis)
            if stmt:
                exclusions.add(stmt)

        # Track which indices need thesis generation (both missing/empty)
        theses_indices = []
        for i, (thesis, antithesis) in enumerate(normalized):
            if indices_to_generate is not None and i not in indices_to_generate:
                continue
            if not self._has_content(thesis) and not self._has_content(antithesis):
                theses_indices.append(i)

        # Extract missing theses for empty positions
        generated_theses: list[DialecticalComponent] = []
        if len(theses_indices) == 1:
            t = await self._thesis_extractor.extract_single_thesis(
                source=source, not_like_these=list(exclusions)
            )
            exclusions.add(t.statement)
            generated_theses = [t]
        elif len(theses_indices) > 1:
            ts = await self._thesis_extractor.extract_multiple_theses(
                source=source, count=len(theses_indices), not_like_these=list(exclusions)
            )
            exclusions.update(t.statement for t in ts)
            generated_theses = ts

        # Initialize result list
        result: list[tuple[DialecticalComponent | None, DialecticalComponent | None]] = [
            (None, None) for _ in range(len(normalized))
        ]

        # Fill in known components and place generated theses
        thesis_counter = 0
        for i, (thesis_item, antithesis_item) in enumerate(normalized):
            # If selective generation is enabled and this index is not in the list
            if indices_to_generate is not None and i not in indices_to_generate:
                # Preserve existing graph nodes or convert strings with content
                t_node = None
                a_node = None

                if isinstance(thesis_item, DialecticalComponent):
                    t_node = thesis_item
                    self._ensure_connected(thesis_item, source, connected_ids)
                elif self._has_content(thesis_item):
                    t_node = self._ensure_component(thesis_item, source, connected_ids)

                if isinstance(antithesis_item, DialecticalComponent):
                    a_node = antithesis_item
                    self._ensure_connected(antithesis_item, source, connected_ids)
                elif self._has_content(antithesis_item):
                    a_node = self._ensure_component(antithesis_item, source, connected_ids)

                result[i] = (t_node, a_node)
                continue

            # Handle each case based on what's provided (treat "" as missing)
            has_thesis = self._has_content(thesis_item)
            has_antithesis = self._has_content(antithesis_item)

            if has_thesis and has_antithesis:
                # Both provided with content
                t_node = self._ensure_component(thesis_item, source, connected_ids)
                a_node = self._ensure_component(antithesis_item, source, connected_ids)
                result[i] = (t_node, a_node)
            elif has_thesis:
                # Thesis provided, antithesis needs generation
                t_node = self._ensure_component(thesis_item, source, connected_ids)
                result[i] = (t_node, None)
            elif has_antithesis:
                # Antithesis provided, thesis needs generation (opposite)
                a_node = self._ensure_component(antithesis_item, source, connected_ids)
                result[i] = (None, a_node)
            elif i in theses_indices:
                # Both empty/missing - use generated thesis
                t_node = generated_theses[thesis_counter]
                thesis_counter += 1
                result[i] = (t_node, None)

        # Collect positions that need opposite generation
        statements_needing_opposites: list[str] = []
        indices_needing_opposites: list[int] = []
        is_thesis_position: list[bool] = []

        for i, (t_node, a_node) in enumerate(result):
            if indices_to_generate is not None and i not in indices_to_generate:
                continue

            if t_node is None and a_node is not None and a_node.statement:
                # Need to generate thesis (opposite of antithesis)
                statements_needing_opposites.append(a_node.statement)
                indices_needing_opposites.append(i)
                is_thesis_position.append(True)
            elif a_node is None and t_node is not None and t_node.statement:
                # Need to generate antithesis (opposite of thesis)
                statements_needing_opposites.append(t_node.statement)
                indices_needing_opposites.append(i)
                is_thesis_position.append(False)

        # Generate all opposites in batch
        generated_opposites: list[DialecticalComponent] = []
        if len(statements_needing_opposites) == 1:
            opp = await self._antithesis_extractor.extract_single_antithesis(
                source=source,
                thesis=statements_needing_opposites[0],
                not_like_these=list(exclusions)
            )
            generated_opposites = [opp]
        elif len(statements_needing_opposites) > 1:
            generated_opposites = await self._antithesis_extractor.extract_multiple_antitheses(
                source=source,
                theses=statements_needing_opposites,
                not_like_these=list(exclusions)
            )

        # Place generated opposites in correct positions
        for idx, opp_node, is_t_pos in zip(indices_needing_opposites, generated_opposites, is_thesis_position):
            t_node, a_node = result[idx]
            if is_t_pos:
                result[idx] = (opp_node, a_node)
            else:
                result[idx] = (t_node, opp_node)

        # Create OPPOSITE_OF relationships between thesis and antithesis
        final_result: list[tuple[DialecticalComponent, DialecticalComponent]] = []
        for t_node, a_node in result:
            if t_node and a_node and t_node.statement and a_node.statement:
                # Create OPPOSITE_OF relationship (bidirectional)
                t_node.oppositions.connect(a_node)
            final_result.append((t_node, a_node))

        return final_result

    def _ensure_connected(
        self,
        component: DialecticalComponent,
        source: Union[Input, Ideas],
        connected_ids: set[str],
    ) -> None:
        """Ensure component is connected to source via HAS_STATEMENT.

        Args:
            component: The component to connect
            source: The Input/Ideas source node
            connected_ids: Pre-computed set of already-connected identities (mutated on connect)
        """
        if component.hash not in connected_ids:
            source.statements.connect(component)
            connected_ids.add(component.hash)

    def _ensure_component(
        self,
        item: GivenItem,
        source: Union[Input, Ideas],
        connected_ids: set[str],
    ) -> DialecticalComponent:
        """
        Ensure item is a graph node connected to source.

        If item is already a DialecticalComponent, ensure it's connected to source.
        If item is a non-empty string, create a new component and connect it.

        Args:
            item: String or DialecticalComponent
            source: The Input/Ideas source node
            connected_ids: Pre-computed set of already-connected identities (mutated on connect)

        Raises:
            ValueError: If item is None, empty string, or unexpected type
        """
        if isinstance(item, DialecticalComponent):
            self._ensure_connected(item, source, connected_ids)
            return item
        elif isinstance(item, str) and item:  # Non-empty string
            component = DialecticalComponent(statement=item)
            component.commit()
            source.statements.connect(component)
            connected_ids.add(component.hash)
            return component
        else:
            raise ValueError(f"Cannot create component from: {item!r}")
