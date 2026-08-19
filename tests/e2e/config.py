"""
Bench configuration — models come from the environment, never from code.

Model IDs are not secrets, but credentials are, and the two travel together in
`.env`. Keeping the model choice there too means one place to change when a
deployment has different Bedrock access, and no reason for anyone to paste an
ARN or an account-scoped inference profile into a committed file.

Env vars (all optional; defaults below are the value the code uses):

    DIALEXITY_E2E_TIER_WEAK   weaker tier under test
    DIALEXITY_E2E_TIER_STRONG stronger tier under test
    DIALEXITY_E2E_SIMULATOR   model that plays the person (fixed across arms)
    DIALEXITY_E2E_JUDGE       model that scores transcripts

Why a distinct model for the judge and the simulator
====================================================
The judge must not be the model under test: asking a model to score its own
transcript against a rival's invites self-preference, and the design leans on
the judge only where a machine scorer cannot reach. The simulator is held fixed
across arms so the opponent's quality never co-varies with the tier — if the
simulator got stronger alongside the arm, a "durable" delta could just be a
stronger interlocutor.
"""

from __future__ import annotations

import os
from typing import Optional

from pydantic import BaseModel, Field

#: Defaults chosen so a plain `pytest --real-llm` run is meaningful without any
#: bench-specific env: two tiers a generation apart, a mid model as the
#: simulated person, and a judge from a different family-position than either
#: tier under test.
DEFAULT_TIER_WEAK = "bedrock/global.anthropic.claude-haiku-4-5-20251001-v1:0"
DEFAULT_TIER_STRONG = "bedrock/global.anthropic.claude-sonnet-5"
DEFAULT_SIMULATOR = "bedrock/global.anthropic.claude-sonnet-5"
DEFAULT_JUDGE = "bedrock/global.anthropic.claude-fable-5"


class E2EConfig(BaseModel):
    """Which models play which role. Tier order is weakest -> strongest."""

    tiers: dict[str, str] = Field(
        description="Tier label -> model id. Order matters: the first key is "
        "the weakest tier, and the depreciating/durable classification reads "
        "the trend from first to last."
    )
    simulator_model: str
    judge_model: str

    @property
    def tier_order(self) -> list[str]:
        return list(self.tiers)

    @classmethod
    def from_env(cls, *, tiers: Optional[list[str]] = None) -> "E2EConfig":
        """Read model choices from the environment.

        `tiers` selects a subset by label ("weak", "strong"). A single-tier run
        is allowed and cheap, but the report will say plainly that no delta can
        be classified from it.
        """
        available = {
            "weak": os.getenv("DIALEXITY_E2E_TIER_WEAK", DEFAULT_TIER_WEAK),
            "strong": os.getenv("DIALEXITY_E2E_TIER_STRONG", DEFAULT_TIER_STRONG),
        }
        if tiers:
            unknown = [t for t in tiers if t not in available]
            if unknown:
                raise ValueError(
                    f"Unknown tier labels: {unknown}. Available: {sorted(available)}"
                )
            selected = {t: available[t] for t in tiers}
        else:
            selected = available
        return cls(
            tiers=selected,
            simulator_model=os.getenv("DIALEXITY_E2E_SIMULATOR", DEFAULT_SIMULATOR),
            judge_model=os.getenv("DIALEXITY_E2E_JUDGE", DEFAULT_JUDGE),
        )
