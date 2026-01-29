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
    dto: DialecticalComponentDto
) -> DialecticalComponent:
    """
    Convert DialecticalComponentDto to graph-native DialecticalComponent.

    This function handles the conversion from AI-returned DTOs to persisted graph nodes.
    If the DTO includes an explanation, a Rationale node is created and linked.

    Args:
        dto: DialecticalComponentDto from AI call
        graph_db: Injected graph database connection

    Returns:
        Saved DialecticalComponent graph node

    Example:
        # After AI call returns DTO
        component_dto = await extract_thesis()  # Returns DialecticalComponentDto
        component = component_from_dto(component_dto)  # Convert to graph model
        # Now work with graph model
        from dialectical_framework.graph.relationships.polarity_relationship import TRelationship
        wu.t.connect(component, relationship=TRelationship(alias='T'))
    """
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
    from dialectical_framework.graph.nodes.rationale import Rationale

    # Create component node
    component = DialecticalComponent(statement=dto.statement)
    component.save()

    # Add rationale if explanation provided
    if dto.explanation:
        rationale = Rationale(text=dto.explanation)
        rationale.save()
        component.rationales.connect(rationale)

    return component


@inject
def components_from_dtos(
    dtos: list[DialecticalComponentDto]
) -> list[DialecticalComponent]:
    """
    Convert list of DialecticalComponentDtos to graph-native components.

    Batch conversion helper for multiple components.

    Args:
        dtos: List of DialecticalComponentDto from AI call
        graph_db: Injected graph database connection

    Returns:
        List of saved DialecticalComponent graph nodes

    Example:
        # After AI call returns multiple DTOs
        component_dtos = await extract_components()  # Returns list[DialecticalComponentDto]
        components = components_from_dtos(component_dtos)  # Convert to graph models
    """
    return [component_from_dto(dto) for dto in dtos]
