from pydantic import BaseModel, Field, ConfigDict

from dialectical_framework.wheel_segment import WheelSegment


class Transition(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    source: WheelSegment = Field(description="Source segment of the wheel.")
    target: WheelSegment = Field(description="Target segment of the wheel.")

    text: str | None = Field(default=None, description="The useful summary of the transition.")


