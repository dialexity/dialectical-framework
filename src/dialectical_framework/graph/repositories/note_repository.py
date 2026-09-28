"""
NoteRepository: the durable half of the consent surface's note queue.

All queries are scoped by sid (injected from DI context). Listing is
committed-only by rule (`hash IS NOT NULL`).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional, Union

from dependency_injector.wiring import Provide, inject
from gqlalchemy import Memgraph, Neo4j

from dialectical_framework.enums.di import DI

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.note import Note


class NoteRepository:
    """Notes the person asked to keep, and whether each was planted yet."""

    @inject
    def find_unplanted(
        self,
        sid: Optional[str] = Provide[DI.sid],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
    ) -> list[Note]:
        """Committed notes nobody has planted, oldest first.

        This is what the off-turn task drains, in whichever process runs it —
        the in-memory queue is only the trigger. Fail-soft but never silent: a
        read fault here would otherwise look exactly like "nothing was kept".
        """
        if not sid:
            return []
        query = """
        MATCH (n:Note {sid: $sid})
        WHERE n.hash IS NOT NULL AND n.planted IS NULL
        RETURN n
        ORDER BY n.committed_at
        """
        try:
            return [r["n"] for r in graph_db.execute_and_fetch(query, {"sid": sid})]
        except Exception:
            logger.exception("Note query failed for sid=%s", sid)
            return []

    @inject
    def count_unplanted(
        self,
        sid: Optional[str] = Provide[DI.sid],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
    ) -> int:
        """How many kept notes are still pending — for the context dump's
        status line, which wants a count and not the notes themselves."""
        if not sid:
            return 0
        query = """
        MATCH (n:Note {sid: $sid})
        WHERE n.hash IS NOT NULL AND n.planted IS NULL
        RETURN count(n) AS pending
        """
        try:
            rows = list(graph_db.execute_and_fetch(query, {"sid": sid}))
            return int(rows[0]["pending"]) if rows else 0
        except Exception:
            logger.exception("Note count failed for sid=%s", sid)
            return 0
