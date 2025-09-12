
from pydantic import Field, BaseModel


class ConstructiveConvergenceTransitionAuditDto(BaseModel):
    feasibility: float = Field(description="Feasibility of the transition, number between 0 and 1")
    key_factors: str = Field(description="Most critical factors affecting feasibility")
    argumentation: str = Field(description="Concise explanation referencing context and evidence")
    success_conditions: str = Field(description="What would need to change to improve feasibility")