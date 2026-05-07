"""
DisplayTextEdit: Concern for editing display text on Statement and Transition nodes.

For Statement: sets `display_text` — a cosmetic override that does NOT affect hash.
For Transition: edits `instruction` directly (it's mutable, not part of hash).

No forking, no new nodes, no LLM calls.

Usage:
    concern = DisplayTextEdit()
    result = await concern.resolve(
        node_hash="abc123...",
        display_text="Shorter wording",
    )

    # Clear display_text
    result = await concern.resolve(
        node_hash="abc123...",
        display_text=None,
    )
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Union

from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.nodes.transition import Transition
from dialectical_framework.graph.repositories.node_repository import NodeRepository


@dataclass
class DisplayTextEditResult:
    """Result of editing display text."""

    node: Optional[Union[Statement, Transition]] = None
    previous_value: Optional[str] = None
    new_value: Optional[str] = None
    error_message: str = ""

    @property
    def is_valid(self) -> bool:
        return self.node is not None and not self.error_message


class DisplayTextEdit(ReasonableConcern[DisplayTextEditResult]):
    """
    Concern for editing display text on committed nodes.

    Supports:
    - Statement.display_text (cosmetic override, text is structural/immutable)
    - Transition.instruction (directly mutable, not part of hash)

    No LLM calls, no hash change, no forking. Just a field update + save().
    """

    def __init__(self) -> None:
        pass

    async def resolve(
        self,
        node_hash: str,
        display_text: Optional[str] = None,
    ) -> DisplayTextEditResult:
        """
        Set or clear display text on a Statement or Transition.

        For Statement: sets display_text (override for immutable text).
        For Transition: sets instruction directly (mutable field).

        Args:
            node_hash: Hash (or prefix) of the node to edit
            display_text: New display text, or None to clear

        Returns:
            DisplayTextEditResult with the updated node
        """

        repo = NodeRepository()
        node = repo.find_by_hash(node_hash)

        if node is None:
            result = DisplayTextEditResult(
                error_message=f"Node '{node_hash}' not found",
            )
            self._report.ok = False
            self._report.summary = result.error_message
            return result

        if not isinstance(node, (Statement, Transition)):
            result = DisplayTextEditResult(
                error_message=f"Node '{node_hash}' is {type(node).__name__}, not Statement or Transition",
            )
            self._report.ok = False
            self._report.summary = result.error_message
            return result

        if not node.is_committed:
            result = DisplayTextEditResult(
                error_message=f"Node '{node_hash}' is not committed — display text only applies to committed nodes",
            )
            self._report.ok = False
            self._report.summary = result.error_message
            return result

        # Apply edit
        if isinstance(node, Statement):
            previous = node.display_text
            node.display_text = display_text
            field_name = "display_text"
        else:
            previous = node.instruction
            node.instruction = display_text
            field_name = "instruction"

        node.save()

        result = DisplayTextEditResult(
            node=node,
            previous_value=previous,
            new_value=display_text,
        )

        action = "Set" if display_text else "Cleared"
        self._report.ok = True
        self._report.summary = f"{action} {field_name} on {node.short_hash}"
        self._report.artifacts["node_hash"] = node.hash
        self._report.artifacts["field"] = field_name
        self._report.artifacts["previous"] = previous
        self._report.artifacts["new"] = display_text

        return result
