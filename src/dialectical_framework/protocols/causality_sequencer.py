"""
Abstract base class for causality sequencing.

Causality sequencers arrange dialectical components or wisdom units into
circular topologies (Cycles or Wheels) by analyzing causal relationships
and estimating transition probabilities.

Two-phase workflow:
1. Structure building: arrange() creates Cycles and Wheels from a Nexus
2. Estimation: estimate() attaches AI-generated Rationale and Estimation nodes

This decoupling allows:
- Creating structures when causality intent is known (no AI needed)
- Retrying estimation on existing committed structures
- Reusing existing Cycles/Wheels if intent matches
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dialectical_framework.graph.mixins.circular_topology_mixin import CircularTopologyMixin
    from dialectical_framework.graph.nodes.cycle import Cycle
    from dialectical_framework.graph.nodes.nexus import Nexus


class CausalitySequencer(ABC):
    """
    Abstract base class for arranging thoughts into circular topologies.

    Implementations analyze relationships between components/wisdom units and
    generate ordered arrangements with probability estimates.

    Workflow:
    1. arrange() - creates Cycles and Wheels from Nexus (or reuses existing)
    2. estimate() - attaches AI-generated Rationale and Estimation nodes
    """

    @abstractmethod
    def arrange(
        self,
        nexus: Nexus,
        intent: str,
    ) -> list[Cycle]:
        """
        Arrange WisdomUnits in a Nexus into Cycles and Wheels (idempotent).

        Creates Cycle nodes (from T components) and Wheel nodes (from WisdomUnits).
        Picks up where it left off:
        - If some Cycles with this intent exist, only creates missing ones
        - If some Wheels exist in a Cycle, only creates missing ones

        Commit behavior follows Nexus state:
        - If Nexus is committed: new Cycles and Wheels are committed
        - If Nexus is uncommitted: new Cycles and Wheels are saved but not committed
          (caller is responsible for committing Nexus first, then Cycles, then Wheels)

        Args:
            nexus: Nexus containing WisdomUnits to arrange.
                   Can be uncommitted or committed - new cycles can be added either way.
            intent: Causality intent (e.g., "preset:balanced", "preset:realistic").

        Returns:
            List of all Cycle nodes (existing + new). Wheels via cycle.wheels.all().
            Commit state of new structures matches Nexus commit state.

        Raises:
            ValueError: If nexus has no WisdomUnits.
        """
        ...

    @abstractmethod
    async def estimate(
        self,
        cycle: CircularTopologyMixin | list[CircularTopologyMixin],
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
