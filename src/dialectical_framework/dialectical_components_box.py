from typing import List

from openai import BaseModel
from pydantic import Field

from dialectical_framework.dialectical_component import DialecticalComponent


class DialecticalComponentsBox(BaseModel):
    dialectical_components: List[DialecticalComponent] = Field(
        ...,
        description="A list of dialectical components. It can be empty when no dialectical components are found. It might also be filled with only one dialectical component if only one is to be found.",
    )
