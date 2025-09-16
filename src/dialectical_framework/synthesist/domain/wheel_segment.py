from __future__ import annotations

from pydantic import ConfigDict, Field, BaseModel
from pydantic.fields import FieldInfo

from dialectical_framework.synthesist.domain.dialectical_component import DialecticalComponent

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

    def _get_dialectical_fields(self) -> dict[str, FieldInfo]:
        """Get only fields that contain DialecticalComponent instances and have aliases."""
        return {
            field_name: field_info
            for field_name, field_info in self.__pydantic_fields__.items()
            if hasattr(field_info, "alias") and field_info.alias is not None
        }

    def is_complete(self):
        return all(v is not None for v in self.model_dump(exclude_none=False).values())

    def is_same(self, other: WheelSegment) -> bool:
        if self == other:
            return True
        if type(self) != type(other):
            return False

        for field in self.alias_to_field.values():
            dc_self = self.get(field)
            dc_other = other.get(field)
            if dc_self is None and dc_other is None:
                continue
            if dc_self is None or dc_other is None:
                return False
            if not dc_self.is_same(dc_other):
                return False
        return True

    def is_set(self, key: str | DialecticalComponent) -> bool:
        """
        True if the given field/alias exists **and** its value is not ``None``.
        >>> ws = WheelSegment()
        >>> ws.is_set("T")
        >>> ws.is_set("t")
        """
        if isinstance(key, DialecticalComponent):
            return (
                any(
                    getattr(self, field).is_same(key)
                    for field in self.alias_to_field.values()
                    if getattr(self, field) is not None
                )
                or self.get(key.alias, None) is not None
            )
        else:
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
        if hasattr(self, field_name):
            value = getattr(self, field_name)
            return value if value is not None else default
        return default

    @property
    def field_to_alias(self) -> dict[str, str]:
        return {
            field_name: field_info.alias
            for field_name, field_info in self._get_dialectical_fields().items()
        }

    @property
    def alias_to_field(self) -> dict[str, str]:
        return {
            field_info.alias: field_name
            for field_name, field_info in self._get_dialectical_fields().items()
        }

    def find_component_by_alias(self, alias: str) -> DialecticalComponent | None:
        """
        Helper method to find a dialectical component within a wheel segment by its alias.
        """
        for f, a in self.field_to_alias.items():
            dc = getattr(self, f)
            if isinstance(dc, DialecticalComponent):
                if dc.alias == alias:
                    return dc

        return None

    def add_indexes_to_aliases(self, human_friendly_index: int):
        """
        Updates the aliases of dialectical components with an index to make them unique.

        This method iterates over the field-to-alias mapping of the object and modifies the alias
        of attributes that are instances of DialecticalComponent. The modified alias includes a
        human-friendly index appended to its base while preserving any existing sign.

        If the index was there, it will be overwritten.

        Parameters:
            human_friendly_index: int
                An index to append to the base of the alias to ensure uniqueness.
        """
        for f, a in self.field_to_alias.items():
            dc = getattr(self, f)
            if isinstance(dc, DialecticalComponent):
                dc.set_human_friendly_index(human_friendly_index)

    def pretty(self) -> str:
        ws_formatted = []
        for f, a in self.field_to_alias.items():
            dc = getattr(self, f)
            if isinstance(dc, DialecticalComponent):
                ws_formatted.append(dc.pretty())
        return "\n\n".join(ws_formatted)

    def __str__(self):
        return self.pretty()
