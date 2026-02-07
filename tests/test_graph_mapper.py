"""
Test DTO to graph-native model conversion.

These tests verify that DTOs from AI calls are correctly converted
to graph-native models.
"""

from dialectical_framework.ai_dto.dialectical_component_dto import DialecticalComponentDto
from dialectical_framework.ai_dto.graph_mapper import component_from_dto, components_from_dtos


def test_component_from_dto_basic():
    """Test converting a simple DialecticalComponentDto to graph component."""

    # Create DTO (simulating AI response)
    dto = DialecticalComponentDto(
        alias="T",
        statement="Democracy empowers citizens"
    )

    # Convert to graph model
    component = component_from_dto(dto)

    # Verify component was created and saved
    assert component._id is not None  # Has database ID
    assert component.statement == "Democracy empowers citizens"

    # Verify no rationale (no explanation provided)
    assert component.rationales.count() == 0


def test_component_from_dto_with_explanation():
    """Test converting DTO with explanation creates linked Rationale."""

    # Create DTO with explanation (simulating AI response)
    dto = DialecticalComponentDto(
        alias="T+",
        statement="Promotes equality",
        explanation="Democracy ensures equal representation and voting rights for all citizens."
    )

    # Convert to graph model
    component = component_from_dto(dto)

    # Verify component created
    assert component._id is not None
    assert component.statement == "Promotes equality"

    # Verify rationale was created and linked
    assert component.rationales.count() == 1
    rationale_result = component.rationales.get()
    assert rationale_result is not None
    rationale = rationale_result[0]
    assert rationale.text == "Democracy ensures equal representation and voting rights for all citizens."


def test_components_from_dtos_batch():
    """Test batch conversion of multiple DTOs."""

    # Create multiple DTOs (simulating AI response)
    dtos = [
        DialecticalComponentDto(
            alias="T",
            statement="Remote work increases productivity"
        ),
        DialecticalComponentDto(
            alias="T+",
            statement="Eliminates commute time",
            explanation="Saves average 54 minutes daily"
        ),
        DialecticalComponentDto(
            alias="T-",
            statement="Can cause isolation"
        )
    ]

    # Batch convert to graph models
    components = components_from_dtos(dtos)

    # Verify all components created
    assert len(components) == 3
    assert all(comp._id is not None for comp in components)

    # Verify statements
    assert components[0].statement == "Remote work increases productivity"
    assert components[1].statement == "Eliminates commute time"
    assert components[2].statement == "Can cause isolation"

    # Verify only second component has rationale
    assert components[0].rationales.count() == 0
    assert components[1].rationales.count() == 1
    assert components[2].rationales.count() == 0
