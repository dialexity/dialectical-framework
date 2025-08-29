from __future__ import annotations

import os
from typing import Optional, Self

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from dialectical_framework.enums.causality_type import CausalityType

class Settings(BaseModel):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
    )

    ai_model: str = Field(..., description="AI model alias/deployment to use.")
    ai_provider: Optional[str] = Field(default=None, description="AI model provider to use.")
    component_length: int = Field(default=7, description="Approximate length in words of the dialectical component.")
    causality_type: CausalityType = Field(default=CausalityType.BALANCED, description="Type of causality in the wheel.")

    @classmethod
    def from_env(cls) -> Self:
        """
        Static method to set up and return a Config instance.
        It uses environment variables or hardcoded defaults for configuration.
        """
        load_dotenv()

        model = os.getenv("DIALEXITY_DEFAULT_MODEL", None)
        provider = os.getenv("DIALEXITY_DEFAULT_MODEL_PROVIDER", None)
        missing = []
        if not model:
            missing.append("DIALEXITY_DEFAULT_MODEL")
        if not provider:
            if "/" not in model:
                missing.append("DIALEXITY_DEFAULT_MODEL_PROVIDER")
            else:
                # We will give litellm a chance to derive the provider from the model
                pass
        if missing:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing)}"
            )

        return cls(
            ai_model=model,
            ai_provider=provider,
            component_length=int(os.getenv("DIALEXITY_DEFAULT_COMPONENT_LENGTH", 7)),
            causality_type=CausalityType(
                os.getenv("DIALEXITY_DEFAULT_CAUSALITY_TYPE", CausalityType.BALANCED.value)
            ),
        )