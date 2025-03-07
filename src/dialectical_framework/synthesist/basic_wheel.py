from __future__ import annotations


from openai import BaseModel
from pydantic import Field

from dialectical_framework.dialectical_component import DialecticalComponent

WHEEL_COMPONENT_ALIAS_MAP = {
    "t_minus": "T-",
    "t": "T",
    "t_plus": "T+",
    "a_plus": "A+",
    "a": "A",
    "a_minus": "A-",
}

class BasicWheel(BaseModel):
    t_minus: DialecticalComponent | None = Field(default=None, description="The negative side of the thesis: T-")
    t: DialecticalComponent | None =  Field(default=None, description="The major thesis of the input: T")
    t_plus: DialecticalComponent | None = Field(default=None, description="The positive side of the thesis: T+")
    a_minus: DialecticalComponent | None = Field(default=None, description="The negative side of the antithesis: A-")
    a: DialecticalComponent | None = Field(default=None, description="The antithesis: A")
    a_plus: DialecticalComponent | None = Field(default=None, description="The positive side of the antithesis: A+")

    class Config:
        populate_by_name = True

        @classmethod
        def alias_generator(cls, string: str) -> str:
            return WHEEL_COMPONENT_ALIAS_MAP.get(string, string)

    def dialectical_component_copy_from(self, wheel: BasicWheel, dialectical_component: str):
        if not hasattr(wheel, dialectical_component):
            setattr(self, dialectical_component, None)
            return

        c: DialecticalComponent | None = getattr(wheel, dialectical_component)
        setattr(self, dialectical_component, c.model_copy() if c else None)

    def __str__(self):
        ini_data = []
        for k, v in self.model_dump().items():
            alias = BasicWheel.Config.alias_generator(k)
            ini_data.append(f"{alias} = {v}")
        return "\n------------------\n".join(ini_data)
