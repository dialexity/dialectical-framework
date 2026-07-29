"""
CreateDxInput: Concern for creating an Input node referencing a Transition via dx:// URI.

Enables the Explorer->Analyst feedback loop: the Analyst creates dx:// Inputs
from Transition nodes discovered during exploration, then processes them
selectively via surface_theses or analyze.
"""

from __future__ import annotations

from typing import Optional, Union

from dependency_injector.wiring import Provide, inject
from gqlalchemy import Memgraph, Neo4j

from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.enums.di import DI
from dialectical_framework.graph.nodes.input import Input
from dialectical_framework.graph.nodes.transition import Transition
from dialectical_framework.graph.repositories.case_repository import \
    CaseRepository
from dialectical_framework.graph.repositories.node_repository import \
    NodeRepository


class CreateDxInput(ReasonableConcern[Input]):
    """
    Creates an Input referencing a Transition node via dx:// URI.

    Programmatic usage:
        concern = CreateDxInput()
        input_node = await concern.resolve(transition_hash="abc1234...")
    """

    @inject
    async def resolve(
        self,
        transition_hash: str,
        sid: Optional[str] = Provide[DI.sid],
    ) -> Input:
        repo = NodeRepository()
        node = repo.find_by_hash(transition_hash, node_type=Transition)

        if node is None:
            raise ValueError(f"No Transition found with hash: {transition_hash}")

        case_repo = CaseRepository()
        case = case_repo.find_by_sid()
        if not case:
            raise ValueError("Case not found for current scope")

        uri = f"dx://{sid}/{node.hash}"
        input_node = Input(content=uri)
        input_node.commit()
        case.inputs.connect(input_node)

        # Stamp provenance into the digest (mutable, hash-excluded) so the
        # round-trip stays closable: whoever processes this input can see
        # which exploration the insight came from without raw Cypher.
        provenance = self._build_provenance_digest(node)
        if provenance:
            input_node.digest = provenance
            input_node.save()

        self._report.node_created(input_node)
        self._report.relationship_created(case.inputs, case, input_node)
        self._report.ok = True
        self._report.summary = (
            f"Created dx:// input referencing Transition {node.short_hash}"
        )
        self._report.artifacts["input_hash"] = input_node.hash
        self._report.artifacts["transition_hash"] = node.hash
        nexus = self._find_source_nexus(node)
        if nexus is not None:
            self._report.artifacts["source_nexus_hash"] = nexus.hash

        return input_node

    @staticmethod
    def _find_source_nexus(transition: Transition):
        """Resolve the Nexus a Transition belongs to (position or wheel edge)."""
        from dialectical_framework.graph.nodes.wheel import Wheel
        from dialectical_framework.graph.rendering import (
            find_nexus_for_cycle, find_nexus_for_transformation,
            find_nexus_for_wheel)
        from dialectical_framework.graph.repositories.transformation_repository import \
            TransformationRepository

        parents = TransformationRepository().find_by_position_transition(
            transition
        )
        if parents:
            return find_nexus_for_transformation(parents[0][0])

        container_result = transition.cycle.get()
        if container_result:
            container, _ = container_result
            if isinstance(container, Wheel):
                return find_nexus_for_wheel(container)
            return find_nexus_for_cycle(container)
        return None

    def _build_provenance_digest(self, transition: Transition) -> Optional[str]:
        """Compose the insight text + origin lineage as the input's digest."""
        text = transition.summary or transition.instruction
        if not text:
            return None

        lines = [text, ""]
        nexus = self._find_source_nexus(transition)
        if nexus is not None:
            intent = f' "{nexus.intent}"' if nexus.intent else ""
            lines.append(
                f"Origin: insight from exploration [[{nexus.short_hash}]]{intent}, "
                f"pathway [[{transition.short_hash}]]."
            )
        else:
            lines.append(
                f"Origin: exploration insight, pathway [[{transition.short_hash}]]."
            )
        return "\n".join(lines)
