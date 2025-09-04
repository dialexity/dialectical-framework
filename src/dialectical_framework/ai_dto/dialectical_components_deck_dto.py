
from pydantic import BaseModel, Field

from dialectical_framework.ai_dto.dialectical_component_dto import \
    DialecticalComponentDto


class DialecticalComponentsDeckDto(BaseModel):
    dialectical_components: list[DialecticalComponentDto] = Field(
        ...,
        description="A list of dialectical components. It can be empty when no dialectical components are found. It might also be filled with only one dialectical component if only one is to be found.",
    )