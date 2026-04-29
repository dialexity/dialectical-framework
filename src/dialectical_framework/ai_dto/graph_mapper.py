"""
Graph mapper for converting DTOs to graph-native nodes.

This module provides simple helper functions to convert DTOs (returned from AI/LLM calls)
into graph-native models backed by Memgraph/Neo4j.

DTOs exist only at the AI boundary - this module handles the immediate conversion
from DTO to graph model.
"""

from __future__ import annotations

from typing import Union, TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from gqlalchemy import Memgraph, Neo4j

from dialectical_framework.ai_dto.statement_dto import StatementDto
from dialectical_framework.enums.di import DI

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.statement import Statement
    from dialectical_framework.graph.nodes.rationale import Rationale


@inject
def statement_from_dto(
    dto: StatementDto,
    graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
) -> Statement:
    """
    Convert StatementDto to graph-native Statement.

    This function handles the conversion from AI-returned DTOs to persisted graph nodes.
    If the DTO includes an explanation, a Rationale node is created and linked.

    Statements are content-addressable - same text = same hash.
    This function looks up by text first to reuse existing statements.

    Args:
        dto: StatementDto from AI call
        graph_db: Injected graph database connection

    Returns:
        Statement graph node (existing or newly created)

    Example:
        # After AI call returns DTO
        statement_dto = await extract_thesis()  # Returns StatementDto
        statement = statement_from_dto(statement_dto)  # Convert to graph model
        # Now work with graph model
        from dialectical_framework.graph.relationships.polarity_relationship import TRelationship
        pp.t.connect(statement, relationship=TRelationship(alias='T'))
    """
    from dialectical_framework.graph.nodes.statement import Statement
    from dialectical_framework.graph.nodes.rationale import Rationale

    # Look up by text - Statements are content-addressable
    # We query by text directly rather than hash because hash includes
    # committed_at (for temporal ordering), making pre-save hash computation impossible
    query = """
        MATCH (c:Statement {text: $text})
        RETURN c
        LIMIT 1
    """
    result = list(graph_db.execute_and_fetch(query, {"text": dto.text}))

    if result:
        # Return existing statement
        existing = result[0]["c"]
        # Still add rationale if explanation provided (context-specific, always new)
        if dto.explanation:
            rationale = Rationale(text=dto.explanation)
            rationale.set_explanation_target(existing)
            rationale.commit()
        return existing

    # Create new statement
    # Use alias as meaning fallback when no taxonomy pointer is available
    component = Statement(text=dto.text, meaning=f"verbatim:{dto.alias}")
    component.commit()

    # Add rationale if explanation provided (context-specific, always new)
    if dto.explanation:
        rationale = Rationale(text=dto.explanation)
        rationale.set_explanation_target(component)
        rationale.commit()

    return component


def statements_from_dtos(
    dtos: list[StatementDto]
) -> list[Statement]:
    """
    Convert list of StatementDtos to graph-native statements.

    Batch conversion helper for multiple statements.

    Args:
        dtos: List of StatementDto from AI call

    Returns:
        List of saved Statement graph nodes

    Example:
        # After AI call returns multiple DTOs
        statement_dtos = await extract_statements()  # Returns list[StatementDto]
        statements = statements_from_dtos(statement_dtos)  # Convert to graph models
    """
    return [statement_from_dto(dto) for dto in dtos]
