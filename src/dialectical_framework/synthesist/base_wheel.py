from __future__ import annotations


from openai import BaseModel
from pydantic import Field, ConfigDict

from dialectical_framework.dialectical_component import DialecticalComponent

ALIAS_T = 'T'
ALIAS_T_PLUS = 'T+'
ALIAS_T_MINUS = 'T-'
ALIAS_A = 'A'
ALIAS_A_PLUS = 'A+'
ALIAS_A_MINUS = 'A-'

class BaseWheel(BaseModel):
    """
    A base class for a wheel in the dialectical framework.
    It's very restrictive, to avoid any additional fields.
    However, it's flexible, that the fields can be set by the field name or by alias.
    """
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )

    def __setattr__(self, name, value):
        # If the attribute name is an alias, use the corresponding field name
        if name in self.alias_to_field:
            super().__setattr__(self.alias_to_field[name], value)
        else:
            # Otherwise use the default behavior
            super().__setattr__(name, value)

    t_minus: DialecticalComponent | None = Field(default=None, description="The negative side of the thesis: T-", alias=ALIAS_T_MINUS)
    t: DialecticalComponent | None =  Field(default=None, description="The major thesis of the input: T", alias=ALIAS_T)
    t_plus: DialecticalComponent | None = Field(default=None, description="The positive side of the thesis: T+", alias=ALIAS_T_PLUS)
    a_minus: DialecticalComponent | None = Field(default=None, description="The negative side of the antithesis: A-", alias=ALIAS_A_MINUS)
    a: DialecticalComponent | None = Field(default=None, description="The antithesis: A", alias=ALIAS_A)
    a_plus: DialecticalComponent | None = Field(default=None, description="The positive side of the antithesis: A+", alias=ALIAS_A_PLUS)

    @property
    def field_to_alias(self):
        return {
            field_name: field_info.alias
            for field_name, field_info in self.__pydantic_fields__.items()
        }

    @property
    def alias_to_field(self):
        return {
            field_info.alias: field_name
            for field_name, field_info in self.__pydantic_fields__.items()
        }

    def dialectical_component_copy_from(self, wheel: BaseWheel, dialectical_component: str):
        if not hasattr(wheel, dialectical_component):
            setattr(self, dialectical_component, None)
            return

        c: DialecticalComponent | None = getattr(wheel, dialectical_component)
        setattr(self, dialectical_component, c.model_copy() if c else None)

    def __str__(self):
        ini_data = []
        for k, v in self.model_dump().items():
            alias = self.field_to_alias.get(k, k)
            ini_data.append(f"{alias} = {v}")
        return "\n------------------\n".join(ini_data)
