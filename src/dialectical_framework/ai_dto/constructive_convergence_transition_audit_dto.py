
from pydantic import Field, BaseModel


class ConstructiveConvergenceTransitionAuditDto(BaseModel):
    key_factors: str = Field(...)
    argumentation: str = Field(...)
    success_conditions: str = Field(...)