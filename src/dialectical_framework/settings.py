from __future__ import annotations

import os
from typing import Optional, Self

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from dialectical_framework.enums.causality_preset import CausalityPreset


class Settings(BaseModel):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
    )

    ai_model: str = Field(..., description="AI model alias/deployment to use.")
    ai_provider: Optional[str] = Field(default=None, description="AI model provider to use.")
    component_length: int = Field(default=7, description="Approximate length in words of the dialectical component.")
    cycle_preset: str = Field(default=CausalityPreset.BALANCED, description="Default preset for causality estimation (e.g., preset:realistic, preset:desirable, preset:feasible, preset:balanced).")
    tarorank_default_transition_probability: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Default probability for transitions without explicit probability in TaroRank scoring. Set to 1.0 for feasibility-only scoring (transitions certain, so Score = P × R^α ≈ R^α). None (default) requires explicit probability evidence on all transitions (no free lunch)."
    )
    tarorank_alpha: float = Field(
        default=1.0,
        ge=0.0,
        description="TaroRank relevance exponent (α) in Score = P × R^α formula. 0 = ignore relevance (Score = P only), 1 = balanced (recommended), >1 = emphasize relevance more."
    )

    # Graph database configuration (Memgraph or Neo4j)
    graph_db_vendor: str = Field(default="memgraph", description="Graph database vendor: 'memgraph' or 'neo4j'")
    graph_db_host: str = Field(default="127.0.0.1", description="Graph database host")
    graph_db_port: int = Field(default=7687, description="Graph database port")
    graph_db_username: Optional[str] = Field(default=None, description="Graph database username (required for Neo4j, optional for Memgraph)")
    graph_db_password: Optional[str] = Field(default=None, description="Graph database password (required for Neo4j, optional for Memgraph)")
    graph_db_encrypted: bool = Field(default=False, description="Use encrypted connection (SSL/TLS)")
    graph_db_client_name: str = Field(default="dialectical_framework", description="Client name for connection identification")

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

        # Handle tarorank_default_transition_probability from environment
        default_prob = 1.0 # Default
        default_prob_str = os.getenv("DIALEXITY_TARORANK_DEFAULT_TRANSITION_PROBABILITY")
        if default_prob_str:
            try:
                prob_value = float(default_prob_str)
                if 0.0 <= prob_value <= 1.0:
                    default_prob = prob_value
            except ValueError:
                pass  # Invalid value, use default of the field

        # Handle tarorank_alpha from environment
        tarorank_alpha = 1.0  # Default
        alpha_str = os.getenv("DIALEXITY_TARORANK_ALPHA")
        if alpha_str:
            try:
                alpha_value = float(alpha_str)
                if 0.0 <= alpha_value <= 1.0:
                    tarorank_alpha = alpha_value
            except ValueError:
                pass  # Invalid value, use default

        return cls(
            ai_model=model,
            ai_provider=provider,
            component_length=int(os.getenv("DIALEXITY_DEFAULT_COMPONENT_LENGTH", 7)),
            cycle_preset=os.getenv("DIALEXITY_DEFAULT_CYCLE_PRESET", CausalityPreset.BALANCED),
            tarorank_default_transition_probability=default_prob,
            tarorank_alpha=tarorank_alpha,
            graph_db_vendor=os.getenv("DIALEXITY_GRAPH_DB_VENDOR", "memgraph"),
            graph_db_host=os.getenv("DIALEXITY_GRAPH_DB_HOST", "127.0.0.1"),
            graph_db_port=int(os.getenv("DIALEXITY_GRAPH_DB_PORT", 7687)),
            graph_db_username=os.getenv("DIALEXITY_GRAPH_DB_USERNAME"),
            graph_db_password=os.getenv("DIALEXITY_GRAPH_DB_PASSWORD"),
            graph_db_encrypted=os.getenv("DIALEXITY_GRAPH_DB_ENCRYPTED", "false").lower() == "true",
            graph_db_client_name=os.getenv("DIALEXITY_GRAPH_DB_CLIENT_NAME", "dialectical_framework"),
        )