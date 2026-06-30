"""
CreateNexus concern: creates an exploration container and connects Perspectives to it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.graph.nodes.nexus import Nexus
from dialectical_framework.graph.nodes.perspective import Perspective
from dialectical_framework.graph.repositories.node_repository import \
    NodeRepository
from dialectical_framework.protocols.has_config import SettingsAware


@dataclass
class CreateNexusResult:
    nexus: Nexus
    perspectives: list[Perspective]


class CreateNexus(SettingsAware, ReasonableConcern[CreateNexusResult]):
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
        preset: Optional[str] = None,
        title: Optional[str] = None,
    ) -> CreateNexusResult:
        if not perspective_hashes:
            raise ValueError("At least one Perspective hash is required.")

        effective_preset = preset if preset is not None else self.settings.cycle_preset

        repo = NodeRepository()
        perspectives: list[Perspective] = []
        for pp_hash in perspective_hashes:
            node = repo.find_by_hash(pp_hash, node_type=Perspective)
            if node is None:
                raise ValueError(f"Perspective not found: {pp_hash}")
            perspectives.append(node)

        nexus = Nexus(intent=intent, preset=effective_preset)
        nexus.commit()

        if title:
            nexus.title = title
            nexus.save()

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
        self._report.artifacts["preset"] = effective_preset

        return CreateNexusResult(nexus=nexus, perspectives=perspectives)
