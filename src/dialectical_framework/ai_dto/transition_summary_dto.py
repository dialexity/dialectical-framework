
from pydantic import Field, BaseModel


class TransitionSummaryDto(BaseModel):
    one_liner: str = Field(..., description="One-liner summary.")
    action_phrase: str = Field(..., description="Action phrase.")