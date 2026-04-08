"""
Abstract base class for causality sequencing.

Causality sequencers arrange dialectical components or wisdom units into
circular topologies (Cycles or Wheels) by analyzing causal relationships
and estimating transition probabilities.

Two-phase workflow:
1. Structure building: arrange() creates Cycles and Wheels from WisdomUnits
2. Estimation: estimate() attaches AI-generated Rationale and Estimation nodes

This decoupling allows:
- Creating structures when causality intent is known (no AI needed)
- Retrying estimation on existing committed structures
- Reusing existing Cycles/Wheels if intent matches
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.cycle import Cycle
    from dialectical_framework.graph.nodes.wheel import Wheel
    from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit


class CausalitySequencer(ABC):
    """
    Abstract base class for arranging thoughts into circular topologies.

    Implementations analyze relationships between components/wisdom units and
    generate ordered arrangements with probability estimates.

    Workflow:
    1. arrange() - creates Cycles and Wheels from WisdomUnits
    2. estimate() - attaches AI-generated Rationale and Estimation nodes
    """

    @abstractmethod
    def arrange(
        self,
        wisdom_units: list[WisdomUnit],
        intent: str,
    ) -> list[Cycle]:
        """
        Arrange WisdomUnits into Cycles and Wheels.

        Creates Cycle nodes (from T components) and Wheel nodes (from WisdomUnits).

        Args:
            wisdom_units: List of committed WisdomUnits to arrange.
            intent: Causality intent (e.g., "preset:balanced", "preset:realistic").

        Returns:
            List of Cycle nodes. Wheels via cycle.wheels.all().

        Raises:
            ValueError: If wisdom_units is empty.
        """
        ...

    @abstractmethod
    async def estimate(
        self,
        cycle: Union[Cycle, Wheel, list[Cycle], list[Wheel]],
        force: bool = False,
    ) -> None:
        """
        Attach AI-generated estimations to committed structure(s) (idempotent).

        Creates Rationale and Estimation nodes directly attached to the structures.
        Source text is derived from the Input nodes linked to the structures' components.

        Idempotent behavior:
        - If ALL structures have estimations and force=False → skip (already complete)
        - If SOME structures are missing estimations → estimate ALL (add new estimations)
        - If NO structures have estimations → estimate all

        Multiple estimations per structure are allowed (analytical layer).
        New estimations are added alongside existing ones when re-estimating.

        Args:
            cycle: Single committed structure or list of structures
            force: If True, always add new estimations even if all structures have them

        Raises:
            ValueError: If cycle is empty.

        Note:
            - Creates Rationale nodes explaining each structure
            - Creates ProbabilityEstimation and RelevanceEstimation nodes
            - Probabilities are normalized across all structures
        """
        ...
