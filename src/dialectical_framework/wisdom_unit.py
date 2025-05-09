from __future__ import annotations


from openai import BaseModel
from pydantic import Field, ConfigDict

from dialectical_framework.dialectical_component import DialecticalComponent

ALIAS_T = "T"
ALIAS_T_PLUS = "T+"
ALIAS_T_MINUS = "T-"
ALIAS_A = "A"
ALIAS_A_PLUS = "A+"
ALIAS_A_MINUS = "A-"


class WisdomUnit(BaseModel):
    """
    A basic "molecule" in the dialectical framework, which makes up a diagonal relationship (complementary opposing pieces of the wheel).
    It's very restrictive to avoid any additional fields.
    However, it's flexible that the fields can be set by the field name or by alias.
    """

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
    a_minus: DialecticalComponent | None = Field(
        default=None,
        description="The negative side of the antithesis: A-",
        alias=ALIAS_A_MINUS,
    )
    a: DialecticalComponent | None = Field(
        default=None, description="The antithesis: A", alias=ALIAS_A
    )
    a_plus: DialecticalComponent | None = Field(
        default=None,
        description="The positive side of the antithesis: A+",
        alias=ALIAS_A_PLUS,
    )

    def is_complete(self):
        return all(v is not None for v in self.model_dump(exclude_none=False).values())

    def is_set(self, key: str) -> bool:
        """
        True if the given field/alias exists **and** its value is not ``None``.
        >>> wu = WisdomUnit()
        >>> wu.is_set("T")
        >>> wu.is_set("t")
        """
        return self.get(key, None) is not None

    def get(
        self, key: str, default: object | None = None
    ) -> DialecticalComponent | None:
        """
        Dictionary-style accessor that understands both *field names* and *aliases*.

        Examples
        --------
        >>> wu = WisdomUnit()
        >>> wu.get("t")      # by field name
        >>> wu.get("T")      # by alias
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
        self, wisdom_unit: WisdomUnit, dialectical_component: str
    ):
        if not hasattr(wisdom_unit, dialectical_component):
            setattr(self, dialectical_component, None)
            return

        c: DialecticalComponent | None = getattr(wisdom_unit, dialectical_component)
        setattr(self, dialectical_component, c.model_copy() if c else None)

    def swap_positions(self, mutate: bool = True) -> WisdomUnit:
        """
        Swap thesis (T, T+, T−) and antithesis (A, A+, A−) components.

        Parameters
        ----------
        mutate : bool, default True
            • True – perform the swap in-place and return *self*
            • False – leave *self* unchanged and return a **new** `WisdomUnit`
              whose positions are swapped.

        Returns
        -------
        WisdomUnit
            The mutated instance (if ``mutate``) or the newly created,
            swapped copy.
        """
        # Choose the object we will modify.
        target: WisdomUnit = self if mutate else self.model_copy()

        # Swap each corresponding pair.
        target.t, target.a = target.a, target.t
        target.t_plus, target.a_plus = target.a_plus, target.t_plus
        target.t_minus, target.a_minus = target.a_minus, target.t_minus

        return target

    def __str__(self):
        ini_data = []
        for k, v in self.model_dump().items():
            alias = self.field_to_alias.get(k, k)
            ini_data.append(f"{alias} = {v}")
        return "\n------------------\n".join(ini_data)
