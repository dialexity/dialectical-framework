"""
NexusAgent: Subagent for creating a Nexus from WisdomUnits.

Takes a list of WisdomUnit hashes and creates a Nexus containing them.
This is a thin wrapper around NexusRepository for agent-based orchestration.

Usage:
    # Programmatic use
    agent = NexusAgent(wisdom_unit_hashes=["abc123...", "def456..."])
    result = await agent.execute()
    print(f"Created Nexus: {result.nexus.short_hash}")

    # LLM tool use
    agent = NexusAgent(wisdom_unit_hashes=[...])
    json_result = await agent.call()  # Returns JSON string
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from mirascope import BaseTool
from pydantic import Field, PrivateAttr

from dialectical_framework.agents.executable_capability import ExecutableCapability
from dialectical_framework.agents.execution_report import ExecutionReport
from dialectical_framework.graph.repositories.nexus_repository import NexusRepository

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.nexus import Nexus


@dataclass
class NexusAgentResult:
    """Result from the NexusAgent."""

    nexus: Nexus
    wisdom_unit_count: int


class NexusAgent(BaseTool, ExecutableCapability[NexusAgentResult]):
    """
    Subagent for creating a Nexus from WisdomUnits.

    This agent wraps NexusRepository to provide a consistent agent interface
    for nexus creation, with reporting and validation.

    Dual interface:
    - execute() returns NexusAgentResult for programmatic use
    - call() returns JSON string for LLM tool use
    """

    wisdom_unit_hashes: list[str] = Field(
        description="List of WisdomUnit hashes (full or prefix) to include in the Nexus"
    )
    intent: Optional[str] = Field(
        default=None,
        description="Optional intent for the Nexus (e.g., 'economic_vs_social')"
    )

    _report: ExecutionReport = PrivateAttr()

    async def call(self) -> str:
        """Execute nexus creation and return ExecutionReport as JSON (for LLM tool use)."""
        await self.execute()
        return str(self._report)

    async def execute(self) -> NexusAgentResult:
        """
        Execute the nexus creation.

        Returns:
            NexusAgentResult with created Nexus and wisdom unit count
        """
        self._report = ExecutionReport(tool=self.__class__.__name__)

        if not self.wisdom_unit_hashes:
            raise ValueError("At least one WisdomUnit hash is required")

        # Use repository to create nexus
        repo = NexusRepository()
        nexus = repo.create_from_wisdom_units(
            wisdom_unit_hashes=self.wisdom_unit_hashes,
            intent=self.intent,
        )

        # Report
        self._report.node_created(nexus)
        wu_count = nexus.wisdom_units.count()
        self._report.artifacts["nexus_hash"] = nexus.short_hash
        self._report.artifacts["wisdom_unit_count"] = wu_count
        self._report.artifacts["intent"] = self.intent
        self._report.summary = (
            f"Created Nexus {nexus.short_hash} with {wu_count} WisdomUnits"
            + (f" (intent: {self.intent})" if self.intent else "")
        )

        return NexusAgentResult(
            nexus=nexus,
            wisdom_unit_count=wu_count,
        )
