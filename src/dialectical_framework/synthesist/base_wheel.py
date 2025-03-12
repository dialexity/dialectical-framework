from __future__ import annotations


from openai import BaseModel
from pydantic import Field, ConfigDict

from dialectical_framework.dialectical_component import DialecticalComponent

class BaseWheel(BaseModel):
    model_config = ConfigDict(
        extra='forbid',  # Disallow any fields not defined here
    )

    t_minus: DialecticalComponent | None = Field(default=None, description="The negative side of the thesis: T-", alias='T-')
    t: DialecticalComponent | None =  Field(default=None, description="The major thesis of the input: T", alias='T')
    t_plus: DialecticalComponent | None = Field(default=None, description="The positive side of the thesis: T+", alias='T+')
    a_minus: DialecticalComponent | None = Field(default=None, description="The negative side of the antithesis: A-", alias='A-')
    a: DialecticalComponent | None = Field(default=None, description="The antithesis: A", alias='A')
    a_plus: DialecticalComponent | None = Field(default=None, description="The positive side of the antithesis: A+", alias='A+')

    def dialectical_component_copy_from(self, wheel: BaseWheel, dialectical_component: str):
        if not hasattr(wheel, dialectical_component):
            setattr(self, dialectical_component, None)
            return

        c: DialecticalComponent | None = getattr(wheel, dialectical_component)
        setattr(self, dialectical_component, c.model_copy() if c else None)

    def __str__(self):
        ini_data = []
        field_to_alias = {
            field_name: field_info.alias
            for field_name, field_info in self.__pydantic_fields__.items()
        }

        for k, v in self.model_dump().items():
            alias = field_to_alias.get(k, k)
            ini_data.append(f"{alias} = {v}")
        return "\n------------------\n".join(ini_data)
