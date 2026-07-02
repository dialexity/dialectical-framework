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

    ai_model: str = Field(..., description="AI model in 'provider/model' format (e.g., 'bedrock/global.anthropic.claude-haiku-4-5-20251001-v1:0').")
    component_length: int = Field(default=7, description="Approximate length in words of the statement.")
    max_wheel_layer: int = Field(default=4, description="Maximum wheel layer (PP count per wheel) to build. Layers above this are skipped regardless of nexus size.")
    cycle_preset: str = Field(default=CausalityPreset.AUTO, description="Default preset for causality estimation (e.g., preset:auto, preset:realistic, preset:desirable, preset:feasible, preset:balanced).")

    # Graph database configuration (Memgraph or Neo4j)
    graph_db_vendor: str = Field(default="memgraph", description="Graph database vendor: 'memgraph' or 'neo4j'")
    graph_db_host: str = Field(default="127.0.0.1", description="Graph database host")
    graph_db_port: int = Field(default=7687, description="Graph database port")
    graph_db_username: Optional[str] = Field(default=None, description="Graph database username (required for Neo4j, optional for Memgraph)")
    graph_db_password: Optional[str] = Field(default=None, description="Graph database password (required for Neo4j, optional for Memgraph)")
    graph_db_encrypted: bool = Field(default=False, description="Use encrypted connection (SSL/TLS)")
    graph_db_client_name: str = Field(default="dialectical_framework", description="Client name for connection identification")

    # Effect logging: directory for JSONL effect logs. None = disabled.
    # When set, graph mutations and tool calls are logged to <dir>/<sid>/<agent>.jsonl
    effect_log_dir: Optional[str] = Field(default=None, description="Directory for effect JSONL logs. None = disabled.")

    # Extended thinking: None = disabled, or one of the levels below.
    # Levels map to provider-specific token budgets (% of max_tokens for Anthropic):
    #   "none"    - disable thinking entirely
    #   "minimal" - minimum budget (1024 tokens)
    #   "low"     - 20% of max_tokens
    #   "medium"  - 40% of max_tokens
    #   "high"    - 60% of max_tokens
    #   "max"     - 80% of max_tokens
    # If the model doesn't support thinking, the setting is silently ignored (warning logged).
    thinking_level: Optional[str] = Field(default=None, description="Extended thinking level. None = disabled.")

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
        if not model:
            raise ValueError(
                "Missing required environment variable: DIALEXITY_DEFAULT_MODEL "
                "(must be in 'provider/model' format, e.g., 'bedrock/global.anthropic.claude-haiku-4-5-20251001-v1:0')"
            )

        return cls(
            ai_model=model,
            component_length=int(os.getenv("DIALEXITY_DEFAULT_COMPONENT_LENGTH", 7)),
            max_wheel_layer=int(os.getenv("DIALEXITY_MAX_WHEEL_LAYER", 4)),
            cycle_preset=CausalityPreset.AUTO,
            graph_db_vendor=os.getenv("DIALEXITY_GRAPH_DB_VENDOR", "memgraph"),
            graph_db_host=os.getenv("DIALEXITY_GRAPH_DB_HOST", "127.0.0.1"),
            graph_db_port=int(os.getenv("DIALEXITY_GRAPH_DB_PORT", 7687)),
            graph_db_username=os.getenv("DIALEXITY_GRAPH_DB_USERNAME"),
            graph_db_password=os.getenv("DIALEXITY_GRAPH_DB_PASSWORD"),
            graph_db_encrypted=os.getenv("DIALEXITY_GRAPH_DB_ENCRYPTED", "false").lower() == "true",
            graph_db_client_name=os.getenv("DIALEXITY_GRAPH_DB_CLIENT_NAME", "dialectical_framework"),
            thinking_level=os.getenv("DIALEXITY_THINKING_LEVEL"),
            effect_log_dir=os.getenv("DIALEXITY_GRAPH_LOG_DIR"),
        )