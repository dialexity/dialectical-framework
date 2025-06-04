from __future__ import annotations

from pydantic import BaseModel, Field, ConfigDict

from dialectical_framework.wheel_segment import WheelSegment


class Transition(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    source: WheelSegment = Field(description="Source segment of the wheel.")
    target: WheelSegment = Field(description="Target segment of the wheel.")

    text: str | None = Field(default=None, description="The useful summary of the transition.")

    def new_with(self, other: Transition) -> Transition:
        # Merge fields from old transition into new one, preserving non-None values from self
        self_dict = self.model_dump()
        other_dict = other.model_dump()

        merged_dict = {**other_dict}  # Start with other values
        # Override with self values that are not None
        for key, value in self_dict.items():
            if value is not None:
                merged_dict[key] = value


        new_t_class: type[Transition] = type(self)
        if not isinstance(other, Transition):
            new_t_class = type(other)

        return new_t_class(**merged_dict)

    def __str__(self):
        str_pieces = [f"{self.source.t.alias} → {self.target.t.alias}"]
        if self.text:
            str_pieces.append(f"Summary: {self.text}")

        return "\n".join(str_pieces)


