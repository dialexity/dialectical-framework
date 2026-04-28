"""
Abstract base class for causality sequencing.

Causality sequencers estimate transition probabilities for Cycles and Wheels
by analyzing causal relationships between dialectical components.

The estimate() method runs AI estimation and returns raw results.
The CausalityEstimation feature handles normalization and database persistence.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.cycle import Cycle
    from dialectical_framework.graph.nodes.wheel import Wheel


@dataclass
class EstimationStructured:
    """Raw AI estimation result for a single structure (Cycle or Wheel)."""

    probability: float  # Raw AI probability (0-1), NOT normalized
    reasoning: str  # Why this sequence might occur
    argumentation: str  # Circumstances where applicable


class CausalitySequencer(ABC):
    """
    Abstract base class for estimating causality in circular topologies.

    Implementations analyze relationships between components and
    generate probability estimates for Cycles and Wheels.

    This is a "dumb" estimator - it runs AI on whatever it gets and returns
    raw results. The CausalityEstimation feature handles orchestration.
    """

    @abstractmethod
    async def estimate(
        self,
        structures: Union[Cycle, list[Cycle], Wheel, list[Wheel]],
    ) -> dict[str, EstimationStructured]:
        """
        Estimate probabilities for structures using AI.

        This is a simple AI estimator - it estimates ALL structures provided
        and returns raw (non-normalized) results. Does NOT touch the database.

        Args:
            structures: Single structure or list of same-type structures
                       (all Cycles OR all Wheels, not mixed)

        Returns:
            Dict mapping structure hash to StructureEstimation with raw AI results

        Raises:
            ValueError: If structures is empty or mixed types
        """
        ...
