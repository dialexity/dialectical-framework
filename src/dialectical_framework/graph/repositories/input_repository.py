"""
InputRepository for querying Input nodes.

All queries are scoped by sid (injected from DI context) to prevent cross-user data leaks.
"""

from __future__ import annotations

from typing import Optional, Union, TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from gqlalchemy import Memgraph, Neo4j

from dialectical_framework.enums.di import DI

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.input import Input


class InputRepository:
    """
    Repository for Input query operations.

    All queries are automatically scoped by sid (injected from DI context).
    """

    # TODO: Inputs that are referencing Statement nodes via dx:// should be excluded I guess, Rationales are ok?
    @inject
    def get_all(
        self,
        sid: Optional[str] = Provide[DI.sid],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
    ) -> list[Input]:
        """
        Get all Input nodes in the current scope.

        Oldest first, matching the sibling repositories. Unordered, the same
        graph rendered a different prompt run to run: this list is what
        `input_context` walks, so the source order in every concern prompt (and
        in the Advisor's `# Sources` line) was whatever Memgraph happened to
        return, which costs prompt-cache hits and makes a bench arm
        irreproducible for no benefit. Allocation is unaffected either way —
        `_allocate` is order-independent by construction — so this moves
        rendering order only.

        Returns full nodes, `content` included. Callers that render nothing but
        identifiers want `all_hashes()` instead: a 400 KB source costs real
        milliseconds to ship and this is on the per-turn context-dump path.

        Args:
            sid: Case ID (injected from DI context)

        Returns:
            List of Input nodes with matching sid
        """
        if not sid:
            return []

        query = """
        MATCH (i:Input)
        WHERE i.sid = $sid AND i.hash IS NOT NULL
        RETURN i
        ORDER BY i.committed_at ASC, id(i) ASC
        """
        results = graph_db.execute_and_fetch(query, {"sid": sid})
        return [record["i"] for record in results if record["i"] is not None]

    @inject
    def all_hashes(
        self,
        sid: Optional[str] = Provide[DI.sid],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
    ) -> list[str]:
        """Hashes of every committed Input in scope, oldest first.

        Same filter and order as `get_all()`, without shipping `content`. The
        `# Sources` line in the context dump renders identifiers and nothing
        else, and it was paying for the full material to do it: measured at
        34 ms for three 400 KB sources and 113 ms for ten, against a flat
        ~2-3 ms here, on a dump that fires on the large majority of turns
        (`tests/probe_source_listing_cost.py`). Negligible for short captures —
        this exists for the pasted-document case, where the cost grows with the
        document and nothing bounds it.

        Returns:
            Full hashes; abbreviate at the render site.
        """
        if not sid:
            return []

        query = """
        MATCH (i:Input)
        WHERE i.sid = $sid AND i.hash IS NOT NULL
        RETURN i.hash AS hash
        ORDER BY i.committed_at ASC, id(i) ASC
        """
        results = graph_db.execute_and_fetch(query, {"sid": sid})
        return [record["hash"] for record in results if record["hash"]]

    @inject
    def analyzed_hashes(
        self,
        sid: Optional[str] = Provide[DI.sid],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
    ) -> set[str]:
        """Hashes of Inputs in scope that already yielded at least one Statement.

        An Input reaches its Statements two ways (see the diagram in
        `nodes/case.py`): the direct `Input-[:HAS_STATEMENT]->Statement`
        shortcut, and the 2-hop provenance path
        `Input-[:DISTILLED_TO]->Ideas-[:HAS_STATEMENT]->Statement`. Extraction
        writes the 2-hop one, so a reader that checks only `input.statements`
        sees every analyzed Input as unanalyzed. Both are counted here, in one
        query for the whole scope rather than one per Input.

        Returns:
            Full hashes; callers holding Input nodes test `inp.hash in result`.
        """
        if not sid:
            return set()

        query = """
        MATCH (i:Input)
        WHERE i.sid = $sid AND i.hash IS NOT NULL
        OPTIONAL MATCH (i)-[:HAS_STATEMENT]->(direct:Statement)
        OPTIONAL MATCH (i)-[:DISTILLED_TO]->(:Ideas)-[:HAS_STATEMENT]->(viaIdeas:Statement)
        WITH i, count(direct) + count(viaIdeas) AS statement_count
        WHERE statement_count > 0
        RETURN i.hash AS hash
        """
        results = graph_db.execute_and_fetch(query, {"sid": sid})
        return {record["hash"] for record in results if record["hash"]}

    @inject
    def find_by_statement_hashes(
        self,
        statement_hashes: list[str],
        sid: Optional[str] = Provide[DI.sid],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
    ) -> dict[str, list[Input]]:
        """Source Inputs per Statement, following both provenance paths.

        The reverse of `analyzed_hashes`: direct `Input-[:HAS_STATEMENT]->` plus
        `Input-[:DISTILLED_TO]->Ideas-[:HAS_STATEMENT]->`. Traversing only the
        direct edge leaves callers with no source text at all, because
        extraction writes the 2-hop path.

        Args:
            statement_hashes: FULL hashes read off Statement nodes. Exact match
                on purpose: these are programmatic, not the abbreviated hashes
                a model or UI hands in, which repositories match by prefix.

        Returns:
            Statement hash -> its source Inputs. Statements with no source
            Input are absent from the mapping.
        """
        if not sid or not statement_hashes:
            return {}

        query = """
        UNWIND $statement_hashes AS statement_hash
        MATCH (s:Statement)
        WHERE s.sid = $sid AND s.hash = statement_hash
        OPTIONAL MATCH (direct:Input)-[:HAS_STATEMENT]->(s)
        WHERE direct.sid = $sid AND direct.hash IS NOT NULL
        OPTIONAL MATCH (viaIdeas:Input)-[:DISTILLED_TO]->(:Ideas)-[:HAS_STATEMENT]->(s)
        WHERE viaIdeas.sid = $sid AND viaIdeas.hash IS NOT NULL
        WITH statement_hash,
             collect(DISTINCT direct) + collect(DISTINCT viaIdeas) AS inputs
        UNWIND inputs AS i
        RETURN statement_hash, i
        """
        results = graph_db.execute_and_fetch(
            query, {"statement_hashes": statement_hashes, "sid": sid}
        )

        by_statement: dict[str, list[Input]] = {}
        for record in results:
            input_node = record["i"]
            if input_node is None:
                continue
            bucket = by_statement.setdefault(record["statement_hash"], [])
            if all(existing.hash != input_node.hash for existing in bucket):
                bucket.append(input_node)
        return by_statement
