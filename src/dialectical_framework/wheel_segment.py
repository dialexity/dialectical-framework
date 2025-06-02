from __future__ import annotations

from openai import BaseModel
from pydantic import ConfigDict, Field

from dialectical_framework.dialectical_component import DialecticalComponent

ALIAS_T = "T"
ALIAS_T_PLUS = "T+"
ALIAS_T_MINUS = "T-"

class WheelSegment(BaseModel):

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
    )

    def __setattr__(self, name, value):
        # If the attribute name is an alias, use the corresponding field name
        if name in self.alias_to_field:
            super().__setattr__(self.alias_to_field[name], value)
        else:
            # Otherwise use the default behavior
            super().__setattr__(name, value)

    t_minus: DialecticalComponent | None = Field(
        default=None,
        description="The negative side of the thesis: T-",
        alias=ALIAS_T_MINUS,
    )
    t: DialecticalComponent | None = Field(
        default=None, description="The major thesis of the input: T", alias=ALIAS_T
    )
    t_plus: DialecticalComponent | None = Field(
        default=None,
        description="The positive side of the thesis: T+",
        alias=ALIAS_T_PLUS,
    )

    def is_complete(self):
        return all(v is not None for v in self.model_dump(exclude_none=False).values())

    def is_set(self, key: str) -> bool:
        """
        True if the given field/alias exists **and** its value is not ``None``.
        >>> ws = WheelSegment()
        >>> ws.is_set("T")
        >>> ws.is_set("t")
        """
        return self.get(key, None) is not None

    def get(
        self, key: str, default: object | None = None
    ) -> DialecticalComponent | None:
        """
        Dictionary-style accessor that understands both *field names* and *aliases*.

        Examples
        --------
        >>> ws = WheelSegment()
        >>> ws.get("t")      # by field name
        >>> ws.get("T")      # by alias
        """
        field_name: str = self.alias_to_field.get(key, key)
        if field_name in self.__pydantic_fields__:
            return getattr(self, field_name)
        return default

    @property
    def field_to_alias(self) -> dict[str, str]:
        return {
            field_name: field_info.alias
            for field_name, field_info in self.__pydantic_fields__.items()
        }

    @property
    def alias_to_field(self) -> dict[str, str]:
        return {
            field_info.alias: field_name
            for field_name, field_info in self.__pydantic_fields__.items()
        }

    def dialectical_component_copy_from(
        self, wheel_segment: WheelSegment, dialectical_component: str
    ):
        if not hasattr(wheel_segment, dialectical_component):
            setattr(self, dialectical_component, None)
            return

        c: DialecticalComponent | None = getattr(wheel_segment, dialectical_component)
        setattr(self, dialectical_component, c.model_copy() if c else None)

    def add_indexes_to_aliases(self, human_friendly_index: int):
        for f, a in self.field_to_alias.items():
            dc = getattr(self, f)
            if isinstance(dc, DialecticalComponent):
                base = a.rstrip('+-')
                sign = a[len(base):]
                dc.alias = f"{base}{human_friendly_index}{sign}"

    def pretty(self) -> str:
        ws_formatted = []
        for f, a in self.field_to_alias.items():
            dc = getattr(self, f)
            if isinstance(dc, DialecticalComponent):
                ws_formatted.append(dc.pretty())
        return "\n\n".join(ws_formatted)

    def __str__(self):
        return self.pretty()
