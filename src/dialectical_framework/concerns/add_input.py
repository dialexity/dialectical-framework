"""
AddInput: Concern for capturing source material into the case.
"""

from __future__ import annotations

from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.graph.nodes.input import Input
from dialectical_framework.graph.repositories.case_repository import CaseRepository


async def capture_input(text: str) -> Input | None:
    """Add a piece of material to the current Case and digest it — the one door.

    "Whoever adds the input, digests it" (CLAUDE.md) was a rule three call
    sites kept separately; this is the rule as a function. The Input is
    content-addressed, so the same text captured twice is one node. A blank
    text captures nothing. Fail-soft on the digest only: `ensure_digest` never
    raises and a short text needs no model call anyway.

    Used by the Advisor's `anchor` for the person's turn, by the one-shot build
    for a host's pasted material (the alsotrue app), and by probes.
    """
    from dialectical_framework.concerns.source_digest import ensure_digest

    text = (text or "").strip()
    if not text:
        return None
    input_node = await AddInput().resolve(content=text)
    if input_node.hash:
        await ensure_digest(input_node.hash)
    return input_node


class AddInput(ReasonableConcern[Input]):
    """
    Captures source material (text or URL) and links it to the current Case.

    Programmatic usage:
        concern = AddInput()
        input_node = await concern.resolve(content="...")
        print(input_node.short_hash)
    """

    async def resolve(self, content: str) -> Input:
        repo = CaseRepository()
        case = repo.require_for_current_scope()

        input_node = Input(content=content)
        input_node.commit()

        already_connected = any(
            node._id == input_node._id for node, _ in case.inputs.all()
        )
        # Creation reports the FULL hash, matching `CreateDxInput`. Prefixes are
        # for rendered context, where they save tokens and lookups tolerate them;
        # at the moment a node comes into existence the caller gets the whole
        # thing, so it has something unambiguous to store.
        if already_connected:
            self._report.ok = True
            self._report.summary = f"Input {input_node.hash} already exists"
            self._report.artifacts["input_hash"] = input_node.hash
            return input_node

        case.inputs.connect(input_node)

        self._report.node_created(input_node)
        self._report.relationship_created(case.inputs, case, input_node)
        self._report.ok = True
        self._report.summary = f"Added input {input_node.hash}"
        self._report.artifacts["input_hash"] = input_node.hash

        return input_node
