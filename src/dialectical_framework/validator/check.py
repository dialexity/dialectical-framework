from openai import BaseModel


class Check(BaseModel):
    is_valid: bool
    explanation: str
