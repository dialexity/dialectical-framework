"""
AddInput: Concern + tool for capturing source material into the case.
"""

from __future__ import annotations

from typing import Annotated

from mirascope import llm
from pydantic import Field

from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.graph.nodes.input import Input
from dialectical_framework.graph.repositories.case_repository import CaseRepository


class AddInput(ReasonableConcern[Input]):
    """
    Captures source material (text or URL) and links it to the current Case.

    Programmatic usage:
        concern = AddInput()
        input_node = await concern.resolve(content="...")
        print(input_node.short_hash)
    """

    async def resolve(self, content: str) -> Input:
        repo = CaseRepository()
        case = repo.find_by_sid()

        if not case:
            raise ValueError("Case not found for current scope")

        input_node = Input(content=content)
        input_node.commit()
        case.inputs.connect(input_node)

        self._report.node_created(input_node)
        self._report.relationship_created(case.inputs, case, input_node)
        self._report.ok = True
        self._report.summary = f"Added input {input_node.short_hash}"
        self._report.artifacts["input_hash"] = input_node.short_hash

        return input_node


@llm.tool
async def add_input(
    content: Annotated[str, Field(description="Source material: user-provided text, URL, or captured conversation fragment")],
) -> str:
    """Add source material for analysis — user-provided text, URL, or captured conversation fragment. Use proactively when the user describes their situation. Not for storing your analytical outputs."""
    concern = AddInput()
    input_node = await concern.resolve(content=content)
    return str(concern.report)
