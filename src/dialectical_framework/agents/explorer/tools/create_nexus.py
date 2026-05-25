"""
CreateNexus: Concern + tool for creating exploration containers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Optional, Union

from dependency_injector.wiring import Provide, inject
from gqlalchemy import Memgraph, Neo4j
from mirascope import llm
from pydantic import Field

from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.enums.causality_preset import CausalityPreset
from dialectical_framework.enums.di import DI
from dialectical_framework.graph.nodes.nexus import Nexus
from dialectical_framework.graph.nodes.perspective import Perspective
from dialectical_framework.graph.repositories.node_repository import NodeRepository


@dataclass
class CreateNexusResult:
    nexus: Nexus
    perspectives: list[Perspective]


class CreateNexus(ReasonableConcern[CreateNexusResult]):
    """
    Creates an exploration container (Nexus) and connects Perspectives to it.

    Programmatic usage:
        concern = CreateNexus()
        result = await concern.resolve(
            intent="figure out the work relationship",
            perspective_hashes=["abc123", "def456"],
        )
        print(result.nexus.short_hash)
    """

    async def resolve(
        self,
        intent: str,
        perspective_hashes: list[str],
        preset: str = CausalityPreset.AUTO,
    ) -> CreateNexusResult:
        if not perspective_hashes:
            raise ValueError("At least one Perspective hash is required.")

        repo = NodeRepository()
        perspectives: list[Perspective] = []
        for pp_hash in perspective_hashes:
            node = repo.find_by_hash(pp_hash, node_type=Perspective)
            if node is None:
                raise ValueError(f"Perspective not found: {pp_hash}")
            perspectives.append(node)

        nexus = Nexus(intent=intent, preset=preset)
        nexus.commit()
        self._report.node_created(nexus)

        for pp in perspectives:
            pp.nexus.connect(nexus)
            self._report.relationship_created(pp.nexus, pp, nexus)

        self._report.ok = True
        self._report.summary = (
            f"Created Nexus {nexus.short_hash} with {len(perspectives)} perspectives"
        )
        self._report.artifacts["nexus_hash"] = nexus.short_hash
        self._report.artifacts["perspective_count"] = len(perspectives)
        self._report.artifacts["preset"] = preset

        return CreateNexusResult(nexus=nexus, perspectives=perspectives)


@llm.tool
async def create_nexus(
    intent: Annotated[str, Field(description="Exploration purpose — what to understand or navigate")],
    perspective_hashes: Annotated[list[str], Field(description="Hashes of Perspectives to include")],
    preset: Annotated[str, Field(description="Estimation strategy: 'preset:auto', 'preset:balanced', 'preset:realistic', 'preset:desirable', 'preset:feasible'")] = "preset:auto",
) -> str:
    """Create a Nexus — an exploration container that groups Perspectives for structural combination into Cycles and Wheels. The intent describes what to explore or navigate."""
    concern = CreateNexus()
    await concern.resolve(intent=intent, perspective_hashes=perspective_hashes, preset=preset)
    return str(concern.report)
