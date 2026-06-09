"""
ExpandNexus concern: adds Perspectives to an existing Nexus.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.graph.nodes.nexus import Nexus
from dialectical_framework.graph.nodes.perspective import Perspective
from dialectical_framework.graph.repositories.node_repository import \
    NodeRepository


@dataclass
class ExpandNexusResult:
    nexus: Nexus
    added: list[Perspective] = field(default_factory=list)
    skipped: list[Perspective] = field(default_factory=list)


class ExpandNexus(ReasonableConcern[ExpandNexusResult]):
    """
    Adds Perspectives to an existing Nexus, skipping already-connected ones.

    Programmatic usage:
        concern = ExpandNexus()
        result = await concern.resolve(
            nexus_hash="abc123",
            perspective_hashes=["def456", "ghi789"],
        )
        print(f"Added {len(result.added)}, skipped {len(result.skipped)}")
    """

    async def resolve(
        self,
        nexus_hash: str,
        perspective_hashes: list[str],
    ) -> ExpandNexusResult:
        if not perspective_hashes:
            raise ValueError("At least one Perspective hash is required.")

        repo = NodeRepository()

        nexus = repo.find_by_hash(nexus_hash, node_type=Nexus)
        if nexus is None:
            raise ValueError(f"Nexus not found: {nexus_hash}")

        perspectives: list[Perspective] = []
        for pp_hash in perspective_hashes:
            node = repo.find_by_hash(pp_hash, node_type=Perspective)
            if node is None:
                raise ValueError(f"Perspective not found: {pp_hash}")
            perspectives.append(node)

        existing_hashes = {pp.hash for pp, _ in nexus.perspectives.all()}
        added: list[Perspective] = []
        skipped: list[Perspective] = []

        for pp in perspectives:
            if pp.hash not in existing_hashes:
                pp.nexus.connect(nexus)
                self._report.relationship_created(pp.nexus, pp, nexus)
                existing_hashes.add(pp.hash)
                added.append(pp)
            else:
                skipped.append(pp)

        self._report.ok = True
        self._report.summary = (
            f"Expanded Nexus {nexus.short_hash}: added {len(added)} perspectives"
            + (f", skipped {len(skipped)} already connected" if skipped else "")
        )
        self._report.artifacts["nexus_hash"] = nexus.short_hash
        self._report.artifacts["added_count"] = len(added)
        self._report.artifacts["skipped_count"] = len(skipped)

        return ExpandNexusResult(nexus=nexus, added=added, skipped=skipped)
