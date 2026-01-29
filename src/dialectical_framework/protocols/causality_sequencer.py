"""
Protocol interface for causality sequencing.

Causality sequencers arrange dialectical components or wisdom units into
circular topologies (Cycles or Wheels) by analyzing causal relationships
and estimating transition probabilities.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, Protocol, Union, overload

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.cycle import Cycle
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
    from dialectical_framework.graph.nodes.wheel import Wheel
    from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit


class CausalitySequencer(Protocol):
    """
    Protocol for arranging thoughts into circular topologies.

    Implementations analyze relationships between components/wisdom units and
    generate ordered arrangements with probability estimates. The sequencer handles:

    - Generating candidate sequences from input thoughts
    - Estimating arrangement probabilities via AI analysis
    - Normalizing probabilities across competing arrangements
    - Creating graph-native Cycle or Wheel objects with Transition nodes

    Return type depends on input:
    - **DialecticalComponents** → returns **Cycles** (thesis-level ordering)
    - **WisdomUnits** → returns **Wheels** (detailed T+A arrangement)
    """

    @overload
    async def arrange(
        self,
        thoughts: list[DialecticalComponent],
        *,
        text: str,
    ) -> list[Cycle]: ...

    @overload
    async def arrange(
        self,
        thoughts: list[WisdomUnit],
        *,
        text: str,
    ) -> list[Wheel]: ...

    @abstractmethod
    async def arrange(
        self,
        thoughts: Union[list[WisdomUnit], list[DialecticalComponent]],
        *,
        text: str,
    ) -> Union[list[Cycle], list[Wheel]]:
        """
        Arrange thoughts into circular topologies with normalized probabilities.

        Analyzes the provided thoughts, generates candidate sequences, estimates
        their probabilities, and returns graph-native objects sorted by likelihood.

        Args:
            thoughts: Input thoughts to arrange:
                - list[DialecticalComponent]: Returns Cycles (thesis-level ordering)
                - list[WisdomUnit]: Returns Wheels (detailed T+A arrangement)
            text: The source text context for AI analysis

        Returns:
            - list[Cycle] when given DialecticalComponents
            - list[Wheel] when given WisdomUnits

            Each returned object contains:
            - Transition nodes linking components in sequence
            - Rationale with reasoning explanation and argumentation
            - Normalized probability reflecting competitive strength

        Raises:
            ValueError: If thoughts list is empty or contains unsupported count.

        Note:
            - Caller must convert strings/DTOs to DialecticalComponents before calling
            - All arrangements are estimated together for probability normalization
            - Probabilities sum to 1.0 across returned objects
            - Wheels are NOT connected to any Cycle - caller must connect them
        """
        ...
