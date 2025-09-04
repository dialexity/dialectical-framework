from __future__ import annotations

import re
from statistics import geometric_mean

from pydantic import BaseModel, Field

from dialectical_framework.protocols.assessable import Assessable


class DialecticalComponent(Assessable):
    alias: str = Field(
        ...,
        description="The user friendly name of the dialectical component such as T, A, T+, A+, etc.",
    )
    statement: str = Field(
        ...,
        description="The dialectical component value that is provided after analysis.",
    )
    explanation: str = Field(
        default="",
        description="The explanation how the dialectical component (statement) is derived.",
    )

    probability: float = Field(default=1, ge=0.0, le=1.0)

    def calculate_contextual_fidelity(self, *, mutate: bool = True) -> float:
        """
        This method doesn't make sense as it doesn't calculate anything, but if someone calls it, we will return 1.0.
        The contextual fidelity should be set directly on the component by someone who is able to estimate it (thesis extractor or so)
        """

        all_fidelities = []

        # Collect fidelities from wisdom-unit-level rationales/opinions
        all_fidelities.extend(self._calculate_contextual_fidelity_for_rationale_rated())

        if not all_fidelities:
            # Someone needs to assign it, it cannot be derived from anything
            fidelity = self.contextual_fidelity if self.contextual_fidelity is not None else 1.0
        else:
            if self.contextual_fidelity is not None:
                all_fidelities.append(self.contextual_fidelity * self.rating)
            fidelity = geometric_mean(all_fidelities)

        if mutate:
            self.contextual_fidelity = fidelity

        return fidelity

    def calculate_probability(self, *, mutate: bool = True) -> float | None:
        """
        This method doesn't make sense as it doesn't calculate anything, but if someone calls it, we will return 1.0.
        """

        # A statement is a fact, so probability is always 1.0
        probability = self.probability if self.probability is not None else 1.0

        if mutate:
            self.probability = probability

        return probability

    def is_same(self, other: DialecticalComponent) -> bool:
        """
        Determines if the current object is equal to another object based on their attributes.

        This method compares the `alias` and `statement` attributes of the current object
        with those of another object to check if they are identical.

        Args:
            other: The object to compare against the current object.

        Returns:
            bool: True if both `alias` and `statement` attributes of the objects are
            the same, otherwise False.
        """
        return (
            self == other
            or self.alias == other.alias
            and self.statement == other.statement
        )

    def get_human_friendly_index(self) -> int:
        """
        Converts the alias of an object into a human-friendly integer index.

        This method processes an alias string provided by the object and identifies
        the last sequence of digits as the human-readable integer index. If no index
        can be identified, the method defaults to returning zero.

        Returns:
            int: The extracted integer index if present; otherwise, returns 0.
        """
        # Find the last sequence of digits in the alias
        match = re.search(r"(\d+)(?!.*\d)", self.alias)
        return int(match.group(1)) if match else 0

    def set_human_friendly_index(self, human_friendly_index: int):
        """
        Updates the alias of the object by replacing the last sequence of digits with the
        provided human-friendly index. If the index is 0, removes any existing digits entirely.
        If no digits exist and index > 0, inserts the index before any trailing signs.

        Args:
            human_friendly_index: The integer index to replace the last sequence of digits
            in the alias with. If 0, removes existing digits.
        """
        if human_friendly_index == 0:
            # Remove the last sequence of digits entirely
            self.alias = re.sub(r"(\d+)(?!.*\d)", "", self.alias)
        else:
            # Try to replace existing digits first
            if re.search(r"\d", self.alias):
                # Replace the last sequence of digits with the new index
                self.alias = re.sub(
                    r"(\d+)(?!.*\d)", str(human_friendly_index), self.alias
                )
            else:
                # No digits exist, insert before any trailing signs
                match = re.search(r"([+-]+)$", self.alias)
                if match:
                    # Has trailing signs, insert index before them
                    base = self.alias[: match.start()]
                    signs = match.group(1)
                    self.alias = f"{base}{human_friendly_index}{signs}"
                else:
                    # No trailing signs, just append the index
                    self.alias = f"{self.alias}{human_friendly_index}"

    def pretty(
        self, dialectical_component_label: str | None = None, *, skip_explanation=False
    ) -> str:
        if not dialectical_component_label:
            dialectical_component_label = self.alias
        result = f"{dialectical_component_label} = {self.statement}"
        if self.explanation and not skip_explanation:
            result = f"{result}\nExplanation: {self.explanation}"
        return result

    def __str__(self):
        return self.pretty()
