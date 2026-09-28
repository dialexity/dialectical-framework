"""
Note node: what the person asked to have written down, kept durably on the turn.

The `ON_CONSENT` Advisor's `note` tool used to queue a (thesis, antithesis,
context) triple in process memory and tell the person "it is written down". On
a shared multi-tenant server that promise held only while the worker lived: a
deploy, a crash or a scale-down between the reply and the off-turn plant lost
exactly the thing the consent surface exists to keep. So the note is now a
committed node the moment the tool returns, and the off-turn task — in THIS
process or in whichever process serves the conversation next — reads the
unplanted ones back from the graph, plants each as a tension (`anchor`'s body)
and stamps `planted` with what it produced.

A nonce in the hash, exactly as Decision has one: each "keep that" is its own
speech act, and a repeat with identical wording is a REQUEST — `anchor` on the
same pair again generates an alternative tetrad (the previous readings are fed
in as "generate different interpretations", and the reading on the Perspective
tells the siblings apart), while its statement-level dedup keeps the tension
itself from duplicating. A content-addressed note would have swallowed that
second keep silently. `committed_at` is excluded from the hash (Decision's
override), so the post-commit `save()` that writes `planted` passes the
integrity re-check.

Case-level, no structural container, never in a parent hash. Not an Input:
an Input is source material the digest reads; a note is an instruction to plant
one specific tension, and its thesis goes to `anchor` verbatim.
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any, Optional

from dialectical_framework.graph.nodes.base_node import BaseNode


class Note(BaseNode, label="Note"):
    """A tension the person asked to keep, waiting to be planted off the turn.

    Fields:
        thesis: the position, in their terms (REQUIRED — `anchor`'s `thesis`).
        antithesis: the opposing force if they named one; None = discover it.
        context: their own specifics behind it (`anchor`'s `context`).
        planted: metadata, mutable, NOT in the hash. None = pending; otherwise
            the comma-joined perspective hashes the plant produced (or a short
            marker when the report carried none). Read by
            `NoteRepository.find_unplanted` and by the context dump's
            "Unfinished" section; folded into `CaseRepository.scope_fingerprint`
            so the render cache sees it move.
    """

    thesis: str
    antithesis: Optional[str] = None
    context: Optional[str] = None
    # One keep, one node — see the module docstring. Fresh per instance, as on
    # Decision; `clone()` gets a new one for the same reason Decision's does.
    nonce: str

    # metadata (mutable post-commit, NOT part of hash)
    planted: Optional[str] = None

    def __init__(self, **data: Any) -> None:
        if "nonce" not in data:
            data["nonce"] = str(uuid.uuid4())
        super().__init__(**data)

    def clone(self, destination_sid: Optional[str] = None) -> Note:
        cloned = super().clone(destination_sid)
        cloned.nonce = str(uuid.uuid4())
        return cloned

    def _collect_structure_hash_parts(self) -> list[str]:
        return [self.thesis, self.antithesis or "", self.context or "", self.nonce]

    def compute_hash(self) -> str:
        """sha256 of thesis + antithesis + context + nonce. No committed_at."""
        combined = "\n".join(self._collect_structure_hash_parts())
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()

    def commit(self, *args, **kwargs) -> Note:
        if not (self.thesis or "").strip():
            raise ValueError("Note requires a thesis before commit.")
        super().commit(*args, **kwargs)
        return self

    def __repr__(self) -> str:
        """Debug representation (may truncate)."""
        preview = self.thesis[:47] + "..." if len(self.thesis) > 50 else self.thesis
        hash_str = self.hash[:7] if self.is_committed else "uncommitted"
        state = "planted" if self.planted else "pending"
        return f"Note({hash_str}, {state}, thesis='{preview}')"

    def __str__(self) -> str:
        """Human-readable representation. LLM-visible — never truncate."""
        if self.antithesis:
            return f"{self.thesis} vs {self.antithesis}"
        return self.thesis
