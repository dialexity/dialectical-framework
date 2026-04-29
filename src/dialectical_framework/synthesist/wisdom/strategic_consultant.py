from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional, List

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.statement import Statement
    from dialectical_framework.graph.nodes.transition import Transition
    from dialectical_framework.graph.nodes.wheel import Wheel
    from dialectical_framework.graph.wheel_segment import WheelSegment

from dialectical_framework.brain import Brain
from dialectical_framework.protocols.has_brain import HasBrain


class StrategicConsultant(ABC, HasBrain):
    def __init__(
        self,
        *,
        text: str,
        wheel: Wheel,
        brain: Optional[Brain] = None,
    ):
        self._text = text
        self._wheel = wheel
        self._brain = brain

    @property
    def brain(self) -> Brain:
        return super().brain if self._brain is None else self._brain

    @staticmethod
    def find_duplicate_transition(
        existing_transitions: List[Transition],
        source_comp: Statement,
        target_comp: Statement
    ) -> Optional[Transition]:
        """
        Find if a transition with the same source/target already exists.

        Compares transitions by their source and target component node IDs.
        This is robust against component renaming/re-indexing.

        Args:
            existing_transitions: List of transitions to search through
            source_comp: Source component to match
            target_comp: Target component to match

        Returns:
            Existing transition if found, None otherwise
        """
        new_source_id = source_comp._id
        new_target_id = target_comp._id

        for t in existing_transitions:
            t_source_result = t.source.get()
            t_target_result = t.target.get()

            if t_source_result and t_target_result:
                t_source_comp, _ = t_source_result
                t_target_comp, _ = t_target_result

                if t_source_comp._id == new_source_id and t_target_comp._id == new_target_id:
                    return t

        return None

    @abstractmethod
    async def think(self, focus: WheelSegment) -> list[Transition]:
        """
        Analyze the given wheel segment and create/update transitions.

        This method should:
        1. Generate insights using LLM
        2. Check for existing transitions to avoid duplicates
        3. Create new transitions or update existing ones with new rationales
        4. Persist all changes to the database

        Args:
            focus: The wheel segment to analyze

        Returns:
            List of newly created transitions (empty list if only updated existing)
        """
        ...
