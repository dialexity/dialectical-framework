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

from dialectical_framework.ai_dto.dialectical_component_dto import DialecticalComponentDto
from dialectical_framework.enums.di import DI

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
    from dialectical_framework.graph.nodes.rationale import Rationale


@inject
def component_from_dto(
    dto: DialecticalComponentDto,
    graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
) -> DialecticalComponent:
    """
    Convert DialecticalComponentDto to graph-native DialecticalComponent.

    This function handles the conversion from AI-returned DTOs to persisted graph nodes.
    If the DTO includes an explanation, a Rationale node is created and linked.

    DialecticalComponents are content-addressable - same statement = same hash.
    This function looks up by hash first to reuse existing components.

    Args:
        dto: DialecticalComponentDto from AI call
        graph_db: Injected graph database connection

    Returns:
        DialecticalComponent graph node (existing or newly created)

    Example:
        # After AI call returns DTO
        component_dto = await extract_thesis()  # Returns DialecticalComponentDto
        component = component_from_dto(component_dto)  # Convert to graph model
        # Now work with graph model
        from dialectical_framework.graph.relationships.polarity_relationship import TRelationship
        pp.t.connect(component, relationship=TRelationship(alias='T'))
    """
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
    from dialectical_framework.graph.nodes.rationale import Rationale

    # Look up by statement - DialecticalComponents are content-addressable
    # We query by statement directly rather than hash because hash includes
    # committed_at (for temporal ordering), making pre-save hash computation impossible
    query = """
        MATCH (c:DialecticalComponent {statement: $statement})
        RETURN c
        LIMIT 1
    """
    result = list(graph_db.execute_and_fetch(query, {"statement": dto.statement}))

    if result:
        # Return existing component
        existing = result[0]["c"]
        # Still add rationale if explanation provided (context-specific, always new)
        if dto.explanation:
            rationale = Rationale(text=dto.explanation)
            rationale.set_explanation_target(existing)
            rationale.commit()
        return existing

    # Create new component
    component = DialecticalComponent(statement=dto.statement)
    component.commit()

    # Add rationale if explanation provided (context-specific, always new)
    if dto.explanation:
        rationale = Rationale(text=dto.explanation)
        rationale.set_explanation_target(component)
        rationale.commit()

    return component


def components_from_dtos(
    dtos: list[DialecticalComponentDto]
) -> list[DialecticalComponent]:
    """
    Convert list of DialecticalComponentDtos to graph-native components.

    Batch conversion helper for multiple components.

    Args:
        dtos: List of DialecticalComponentDto from AI call

    Returns:
        List of saved DialecticalComponent graph nodes

    Example:
        # After AI call returns multiple DTOs
        component_dtos = await extract_components()  # Returns list[DialecticalComponentDto]
        components = components_from_dtos(component_dtos)  # Convert to graph models
    """
    return [component_from_dto(dto) for dto in dtos]
