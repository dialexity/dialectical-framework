from typing import Optional, List

from pydantic import BaseModel, Field

from dialectical_framework.dialectical_component import DialecticalComponent


class Rationale(BaseModel):
    text: Optional[str] = Field(default=None)
    summary: Optional[str] = Field(default=None)
    theses: List[DialecticalComponent] = Field(default_factory=list, description="The theses of the rationale.")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="The confidence of the agent in the rationale.")