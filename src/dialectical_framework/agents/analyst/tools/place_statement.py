"""
PlaceStatement: Tool for recognizing whether a statement already exists in the graph.
"""

from __future__ import annotations

from typing import Annotated

from mirascope import llm
from pydantic import Field

from dialectical_framework.concerns.statement_placement import StatementPlacement


@llm.tool
async def place_statement(
    statement: Annotated[str, Field(description="The statement/concept to look up in the graph")],
    context: Annotated[str, Field(description="Optional conversation context to help match")] = "",
) -> str:
    """Check if a statement already exists in the graph and where it sits (which Perspective, at what position). Returns match info or 'not found'. Does not create anything — use surface_theses or find_polarities to introduce new statements."""
    concern = StatementPlacement()
    await concern.resolve(statement=statement, text=context)
    return str(concern.report)
