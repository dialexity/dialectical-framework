"""
CreateDxInput: Creates an Input node referencing a Transition via dx:// URI.

Enables the Explorer→Analyst feedback loop: the Analyst creates dx:// Inputs
from Transition nodes discovered during exploration, then processes them
selectively via surface_theses or analyze.
"""

from __future__ import annotations

from typing import Optional, Union

from dependency_injector.wiring import Provide, inject
from gqlalchemy import Memgraph, Neo4j
from mirascope import llm
from pydantic import Field

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

        self._report.node_created(input_node)
        self._report.relationship_created(case.inputs, case, input_node)
        self._report.ok = True
        self._report.summary = (
            f"Created dx:// input referencing Transition {node.short_hash}"
        )
        self._report.artifacts["input_hash"] = input_node.hash
        self._report.artifacts["transition_hash"] = node.hash

        return input_node


@llm.tool
async def create_dx_input(
    transition_hash: str = Field(
        description="Hash (or 7+ char prefix) of the Transition node to reference"
    ),
) -> str:
    """Create an Input that references a Transition node via dx:// URI. This feeds the transition's insight back into the analyst pipeline as a new input source that can be processed selectively."""
    concern = CreateDxInput()
    await concern.resolve(transition_hash=transition_hash)
    return str(concern.report)
