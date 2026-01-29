"""
Protocol interface for causality sequencing.

Causality sequencers arrange dialectical components into cycles by analyzing
causal relationships and estimating transition probabilities.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, Protocol, Union

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.cycle import Cycle
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
    from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit


class CausalitySequencer(Protocol):
    """
    Protocol for arranging dialectical components into causal cycles.

    Implementations analyze relationships between components/wisdom units and
    generate ordered cycles with probability estimates. The sequencer handles:

    - Generating candidate sequences from input thoughts
    - Estimating cycle probabilities via AI analysis
    - Normalizing probabilities across competing cycles
    - Creating graph-native Cycle objects with Transition nodes

    Two input modes are supported:
    - **WisdomUnits**: Extracts T/A pairs and generates diagonally symmetric sequences
    - **DialecticalComponents**: Generates all permutations with fixed first element
    """

    @abstractmethod
    async def arrange(
        self,
        thoughts: Union[list[WisdomUnit], list[DialecticalComponent]],
        *,
        text: str,
    ) -> list[Cycle]:
        """
        Arrange thoughts into causal cycles with normalized probabilities.

        Analyzes the provided thoughts (either WisdomUnits or DialecticalComponents),
        generates candidate sequences, estimates their probabilities, and returns
        graph-native Cycle objects sorted by likelihood.

        Args:
            thoughts: Input thoughts to arrange. Either:
                - list[WisdomUnit]: Extracts T/A components for diagonal symmetry
                - list[DialecticalComponent]: Generates permutation sequences
            text: The source text context for AI analysis

        Returns:
            List of Cycle objects sorted by probability (highest first). Each cycle
            contains:
            - Transition nodes linking components in sequence
            - Rationale with reasoning explanation and argumentation
            - Normalized probability reflecting competitive strength

        Raises:
            ValueError: If thoughts list is empty or contains unsupported count.

        Note:
            - Caller must convert strings/DTOs to DialecticalComponents before calling
            - All cycles are estimated together for probability normalization
            - Probabilities sum to 1.0 across returned cycles
        """
        ...
