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
    default_transition_probability: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Default probability for transitions without explicit probability. Set to 1.0 for feasibility-only scoring (transitions certain, so Score = P × R^α ≈ R^α). None (default) requires explicit probability evidence on all transitions (no free lunch)."
    )

    @classmethod
    def from_partial(cls, partial_settings: Optional[Settings] = None) -> Self:
        """
        Create GenerationSettings by merging partial settings with environment defaults.
        Missing fields in partial_settings are filled from Settings.from_env().
        """
        if partial_settings is None:
            return cls.from_env()

        # Get full defaults from environment
        env_defaults = cls.from_env()

        # Convert partial_settings to dict, excluding None values
        partial_dict = partial_settings.model_dump(exclude_none=True) if partial_settings else {}

        # Convert env_defaults to dict
        env_dict = env_defaults.model_dump()

        # Merge: partial_settings override env_defaults
        merged_dict = {**env_dict, **partial_dict}

        # Create new instance from merged data
        return cls(**merged_dict)

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

        # Handle default_transition_probability from environment
        default_prob = None
        default_prob_str = os.getenv("DIALEXITY_DEFAULT_TRANSITION_PROBABILITY")
        if default_prob_str:
            try:
                prob_value = float(default_prob_str)
                if 0.0 <= prob_value <= 1.0:
                    default_prob = prob_value
            except ValueError:
                pass  # Invalid value, use default of the field

        return cls(
            ai_model=model,
            ai_provider=provider,
            component_length=int(os.getenv("DIALEXITY_DEFAULT_COMPONENT_LENGTH", 7)),
            causality_type=CausalityType(
                os.getenv("DIALEXITY_DEFAULT_CAUSALITY_TYPE", CausalityType.BALANCED.value)
            ),
            default_transition_probability=default_prob,
        )