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
    transition_length: int = Field(default=15, description="Approximate maximum length in words of a transition statement (fuller than a component headline).")
    max_wheel_layer: int = Field(default=4, description="Maximum wheel layer (PP count per wheel) to build. Layers above this are skipped regardless of nexus size.")
    cycle_preset: str = Field(default=CausalityPreset.AUTO, description="Default preset for causality estimation (e.g., preset:auto, preset:realistic, preset:desirable, preset:feasible, preset:balanced).")

    # Context-dump quality filter (DialecticalContext). Perspectives below
    # these floors are suppressed from the Advisor's dump (a count line notes
    # them; inspect_node still reaches them). Quality scales: docs/scoring.md.
    # HS bands: 0.5-0.7 moderate, 0.3-0.5 weak, <0.3 barely an antithesis.
    # area (SP) bands: >=0.7 clear differentiation, 0.3-0.7 acceptable,
    # <0.3 aspects blur together.
    # DV: 0-1, naturalness of the dialectical relationship; <0.3 = forced/
    # distorted framing (comparative, no theory-derived cutoff).
    advisor_polarity_quality_min_hs: float = Field(default=0.5, description="Polarity quality floor: suppress perspectives whose antithesis HS (how genuine the T-A opposition is, 0.0-1.0) is below this. 0 disables.")
    # The SP + DV floors together operationalize the paper's acceptance pair
    # (SP > 0.5 AND DV > 0.5 [P0 p.12]) as soft context-pruning — deliberately
    # more conservative defaults than the paper's 0.5 (thresholds are per-LLM
    # calibrated), and pruning the dump, never the graph.
    advisor_perspective_quality_min_sp: float = Field(default=0.3, description="Perspective quality floor: suppress perspectives whose SP (Synthesis Potential = code `area`, differentiation of constructive over destructive aspects, ~0-2) is below this. 0 disables.")
    advisor_perspective_quality_min_dv: float = Field(default=0.3, description="Perspective quality floor: suppress perspectives whose DV (Dialectical Validity — naturalness of the dialectical relationship, 0.0-1.0) is below this. 0 disables.")
    advisor_wheel_quality_top_plausible: int = Field(default=3, description="Max wheels rendered per cycle in the unscoped context dump, top-normalized-%. Counsel-mode (nexus-pinned) dumps are exempt. 0 = unlimited.")

    # Depth budget for the Advisor's SILENT exploration (its `explore` tool).
    # "Rich vs simple" exploration is a runtime budget, not a schema concept:
    # all wheels are always built + estimated (structural, cheap); the budget
    # caps the expensive stages. The Navigator/Explorer path is user-driven
    # and ignores this.
    advisor_max_perspectives_per_exploration: int = Field(default=2, description="Max perspectives woven per silent Advisor explore call; excess is reported as deferred (weave in a follow-up call), never silently dropped. 0 = unlimited.")

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
        Create Settings by merging partial settings with environment defaults.
        Fields not explicitly set on partial_settings are filled from
        Settings.from_env().

        Only EXPLICITLY SET fields override (exclude_unset) — a field left at
        its Pydantic default does not stomp an env-configured value. Fields
        explicitly set to None are also dropped (None never means "unset the
        env value" for any Settings field).
        """
        if partial_settings is None:
            return cls.from_env()

        # Get full defaults from environment
        env_defaults = cls.from_env()

        # Only fields the caller explicitly set, and not to None
        partial_dict = {
            k: v
            for k, v in partial_settings.model_dump(exclude_unset=True).items()
            if v is not None
        }

        # Convert env_defaults to dict
        env_dict = env_defaults.model_dump()

        # Merge: explicitly-set partial fields override env defaults
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
            transition_length=int(os.getenv("DIALEXITY_DEFAULT_TRANSITION_LENGTH", 15)),
            max_wheel_layer=int(os.getenv("DIALEXITY_MAX_WHEEL_LAYER", 4)),
            cycle_preset=CausalityPreset.AUTO,
            advisor_polarity_quality_min_hs=float(os.getenv("DIALEXITY_ADVISOR_POLARITY_QUALITY_MIN_HS", 0.5)),
            advisor_perspective_quality_min_sp=float(os.getenv("DIALEXITY_ADVISOR_PERSPECTIVE_QUALITY_MIN_SP", 0.3)),
            advisor_perspective_quality_min_dv=float(os.getenv("DIALEXITY_ADVISOR_PERSPECTIVE_QUALITY_MIN_DV", 0.3)),
            advisor_wheel_quality_top_plausible=int(os.getenv("DIALEXITY_ADVISOR_WHEEL_QUALITY_TOP_PLAUSIBLE", 3)),
            advisor_max_perspectives_per_exploration=int(os.getenv("DIALEXITY_ADVISOR_MAX_PERSPECTIVES_PER_EXPLORATION", 2)),
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