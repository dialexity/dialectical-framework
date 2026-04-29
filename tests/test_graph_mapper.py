"""
Test DTO to graph-native model conversion.

These tests verify that DTOs from AI calls are correctly converted
to graph-native models.
"""

from dialectical_framework.ai_dto.statement_dto import StatementDto
from dialectical_framework.ai_dto.graph_mapper import statement_from_dto, statements_from_dtos


def test_statement_from_dto_basic():
    """Test converting a simple StatementDto to graph component."""

    # Create DTO (simulating AI response)
    dto = StatementDto(
        alias="T",
        text="Democracy empowers citizens"
    )

    # Convert to graph model
    component = statement_from_dto(dto)

    # Verify component was created and saved
    assert component._id is not None  # Has database ID
    assert component.text == "Democracy empowers citizens"

    # Verify no rationale (no explanation provided)
    assert component.rationales.count() == 0


def test_statement_from_dto_with_explanation():
    """Test converting DTO with explanation creates linked Rationale."""

    # Create DTO with explanation (simulating AI response)
    dto = StatementDto(
        alias="T+",
        text="Promotes equality",
        explanation="Democracy ensures equal representation and voting rights for all citizens."
    )

    # Convert to graph model
    component = statement_from_dto(dto)

    # Verify component created
    assert component._id is not None
    assert component.text == "Promotes equality"

    # Verify rationale was created and linked
    assert component.rationales.count() == 1
    rationale_result = component.rationales.get()
    assert rationale_result is not None
    rationale = rationale_result[0]
    assert rationale.text == "Democracy ensures equal representation and voting rights for all citizens."


def test_statements_from_dtos_batch():
    """Test batch conversion of multiple DTOs."""

    # Create multiple DTOs (simulating AI response)
    dtos = [
        StatementDto(
            alias="T",
            text="Remote work increases productivity"
        ),
        StatementDto(
            alias="T+",
            text="Eliminates commute time",
            explanation="Saves average 54 minutes daily"
        ),
        StatementDto(
            alias="T-",
            text="Can cause isolation"
        )
    ]

    # Batch convert to graph models
    components = statements_from_dtos(dtos)

    # Verify all components created
    assert len(components) == 3
    assert all(comp._id is not None for comp in components)

    # Verify statements
    assert components[0].text == "Remote work increases productivity"
    assert components[1].text == "Eliminates commute time"
    assert components[2].text == "Can cause isolation"

    # Verify only second component has rationale
    assert components[0].rationales.count() == 0
    assert components[1].rationales.count() == 1
    assert components[2].rationales.count() == 0
