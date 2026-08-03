"""
discard: Tool for marking statements/perspectives/decisions as discarded.
"""

from __future__ import annotations

from typing import Annotated

from mirascope import llm
from pydantic import Field

from dialectical_framework.concerns.discard import Discard


@llm.tool
async def discard(
    hash: Annotated[str, Field(description="Hash (or prefix) of the Statement, Perspective, or Decision to discard")],
    reason: Annotated[str, Field(description="Why it's being discarded")] = "discarded",
) -> str:
    """Mark a Statement, Perspective, or Decision as discarded when the user disagrees with it or finds it irrelevant. Uncommitted Perspectives are discarded entirely; committed ones are soft-discarded and filtered from future queries. Will refuse if the target participates in existing Cycles/Wheels — in that case, use edit_perspective to replace it. For a Decision replaced by a newer one, use a reason naming the new decision (e.g. "superseded by [[hash]]")."""
    concern = Discard()
    await concern.resolve(hash=hash, reason=reason)
    return str(concern.report)
