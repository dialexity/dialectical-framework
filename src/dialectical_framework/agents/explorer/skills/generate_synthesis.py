"""
GenerateSynthesis: Skill for generating S+/S- synthesis from a Wheel.

Orchestrates: resolve wheel → verify transformations → gather lower-layer
context → call SynthesisGeneration concern → create Synthesis node → commit.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Optional, TYPE_CHECKING

from dependency_injector.wiring import Provide, inject

from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.concerns.synthesis_generation import (
    SynthesisGeneration,
    SynthesisResult,
)
from dialectical_framework.enums.di import DI
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.nodes.synthesis import (
    POSITION_S_MINUS,
    POSITION_S_PLUS,
    Synthesis,
)
from dialectical_framework.graph.relationships.polarity_relationship import (
    SMinusRelationship,
    SPlusRelationship,
)
from dialectical_framework.graph.relationships.synthesis_of_relationship import (
    SynthesisOfRelationship,
)

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.nexus import Nexus
    from dialectical_framework.graph.nodes.perspective import Perspective
    from dialectical_framework.graph.nodes.wheel import Wheel
    from dialectical_framework.protocols.input_resolver import InputResolver


@dataclass
class GenerateSynthesisResult:
    """Result from GenerateSynthesis skill."""

    synthesis: Synthesis
    is_new: bool = True


class GenerateSynthesis(ReasonableConcern[GenerateSynthesisResult]):
    """
    Skill for generating S+/S- synthesis from a Wheel's Transformations.

    Idempotent: returns existing Synthesis if one already exists for the Wheel.
    """

    def __init__(self, wheel_hash: str) -> None:
        self.wheel_hash = wheel_hash

    async def resolve(self) -> GenerateSynthesisResult:
        """
        Generate synthesis for a Wheel.

        Returns:
            GenerateSynthesisResult with the Synthesis node

        Raises:
            ValueError: If wheel not found or has no Transformations
        """
        wheel = self._resolve_wheel()

        # Check transformations exist
        transformations = wheel.transformations
        if not transformations:
            raise ValueError(
                f"Wheel {wheel.short_hash} has no Transformations — "
                f"run explore_transformations first"
            )

        # Idempotent: return existing synthesis
        existing = self._find_existing_synthesis(wheel)
        if existing:
            self._report.summary = (
                f"Synthesis already exists for Wheel {wheel.short_hash}"
            )
            self._report.artifacts["wheel"] = wheel.short_hash
            self._report.artifacts["existing"] = True
            return GenerateSynthesisResult(synthesis=existing, is_new=False)

        # Gather context
        input_text = await self._get_input_text()
        lower_layer_context = self._build_lower_layer_context(wheel)

        # Call the concern
        concern = SynthesisGeneration()
        result = await concern.resolve(
            wheel=wheel,
            input_text=input_text,
            lower_layer_context=lower_layer_context,
        )
        self._report = self._report.merge(concern.report)

        if result is None:
            raise ValueError(
                f"Synthesis generation failed for Wheel {wheel.short_hash}"
            )

        # Create Synthesis node and wire up
        synthesis = Synthesis()
        synthesis.save()
        self._report.node_created(synthesis)

        synthesis.s_plus.connect(
            result.s_plus_statement,
            relationship=SPlusRelationship(
                alias=POSITION_S_PLUS, heuristic_similarity=None
            ),
        )
        synthesis.s_minus.connect(
            result.s_minus_statement,
            relationship=SMinusRelationship(
                alias=POSITION_S_MINUS, heuristic_similarity=None
            ),
        )
        synthesis.target.connect(wheel, relationship=SynthesisOfRelationship())
        synthesis.commit()

        # Report
        self._report.node_committed(synthesis)
        self._report.artifacts["wheel"] = wheel.short_hash
        self._report.artifacts["s_plus"] = result.s_plus_statement.text
        self._report.artifacts["s_minus"] = result.s_minus_statement.text
        self._report.summary = (
            f"Generated synthesis for Wheel {wheel.short_hash}: "
            f"S+ = \"{result.s_plus_statement.text}\", "
            f"S- = \"{result.s_minus_statement.text}\""
        )

        return GenerateSynthesisResult(synthesis=synthesis)

    def _resolve_wheel(self) -> Wheel:
        """Resolve Wheel from hash or prefix."""
        from dialectical_framework.graph.nodes.wheel import Wheel
        from dialectical_framework.graph.repositories.node_repository import (
            NodeRepository,
        )

        repo = NodeRepository()
        node = repo.find_by_hash(self.wheel_hash, node_type=Wheel)
        if node is None:
            raise ValueError(f"Wheel not found: {self.wheel_hash}")
        return node

    @staticmethod
    def _find_existing_synthesis(wheel: Wheel) -> Optional[Synthesis]:
        """Check if the wheel already has a synthesis."""
        existing = list(wheel.synthesis.all())
        if existing:
            return existing[0][0]
        return None

    @inject
    async def _get_input_text(
        self,
        input_resolver: InputResolver = Provide[DI.input_resolver],
    ) -> str:
        """Get concatenated text from all inputs in scope."""
        from dialectical_framework.graph.repositories.input_repository import (
            InputRepository,
        )

        repo = InputRepository()
        inputs = repo.get_all()

        if not inputs:
            return ""

        texts = []
        for input_node in inputs:
            resolved = await input_resolver.resolve(input_node)
            texts.append(resolved)

        return "\n\n---\n\n".join(texts)

    def _build_lower_layer_context(self, wheel: Wheel) -> str:
        """Find synthesis from sub-wheels (lower PP layers) sharing perspectives."""
        from dialectical_framework.graph.repositories.wheel_repository import (
            WheelRepository,
        )

        pps = wheel._perspectives
        if len(pps) < 2:
            return ""

        wheel_repo = WheelRepository()
        parts: list[str] = []

        # Look one layer down (N-1 perspectives)
        for combo in combinations(pps, len(pps) - 1):
            sub_wheels = wheel_repo.find_by_layer(list(combo))
            for sub_wheel in sub_wheels:
                for synth, _ in sub_wheel.synthesis.all():
                    parts.append(
                        f"Sub-wheel [{sub_wheel.short_hash}]: {synth:positions:0}"
                    )

        return "\n".join(parts)
