"""
Repository for Case node queries.

All queries are scoped by sid (injected from DI context) to prevent cross-user data leaks.
"""

from __future__ import annotations

from typing import Optional, Union, TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from gqlalchemy import Memgraph, Neo4j

from dialectical_framework.enums.di import DI

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.case import Case


class CaseRepository:
    """
    Repository for Case node queries.

    All queries are automatically scoped by sid (injected from DI context).
    """

    @inject
    def find_by_sid(
        self,
        sid: Optional[str] = Provide[DI.sid],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
    ) -> Optional[Case]:
        """
        Find the Case node for the current scope.

        Returns:
            The Case node if found, None otherwise
        """
        if not sid:
            return None

        query = """
        MATCH (c:Case {sid: $sid})
        RETURN c
        """
        results = list(graph_db.execute_and_fetch(query, {"sid": sid}))

        if not results:
            return None

        return results[0]["c"]

    @inject
    def require_for_current_scope(
        self,
        sid: Optional[str] = Provide[DI.sid],
    ) -> Case:
        """The Case for the current scope, or a failure that says what is missing.

        `find_by_sid` returns None for two unrelated reasons — no sid in context
        at all, or a sid with no Case behind it — and callers that collapsed both
        into "Case not found for current scope" left no way to tell them apart.
        One archived e2e cell raised exactly that against a Case that WAS
        committed and in scope, and the flat message is why `tests/e2e/rounds.md`
        still records it as open rather than explained. This does not fix that;
        it makes the next occurrence name which half failed.

        The Case is the application's to create and inject as scope — the
        framework only ever reads it (see `graph/scope_context.py`). So neither
        branch here auto-creates: a Case invented by the framework would be a
        second, empty scope root that the app never learns the sid of, and every
        node written under it would be invisible to the app's own listings.

        Raises:
            MissingScopeError: No sid in context. The caller never entered
                `with scope(case.sid):`, or entered it outside the task that
                ended up running this work.
            ValueError: Scope is set but holds no Case — the application did
                not create one for this sid.
        """
        from dialectical_framework.exceptions.node_errors import MissingScopeError

        if not sid:
            raise MissingScopeError(
                "No scope set, so there is no Case to attach this to. Wrap the "
                "call in `with scope(case.sid):` — the framework never sets "
                "scope itself. Agent chat entry points already guard this, so "
                "reaching here from one means the scope did not propagate into "
                "the task doing the work."
            )

        case = self.find_by_sid()
        if case is None:
            raise ValueError(
                f"No Case exists for scope {sid!r}. The application creates the "
                f"Case and injects its sid as the scope for the round; the "
                f"framework does not create one, because a Case it invented "
                f"would be a scope root the application never sees."
            )
        return case

    @inject
    def scope_fingerprint(
        self,
        sid: Optional[str] = Provide[DI.sid],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
    ) -> Optional[tuple]:
        """A cheap signature of everything in this scope that a render can see.

        Two aggregate queries against the `Node(sid)` index — milliseconds on a
        case whose full render costs seconds — so a reader can ask "has anything
        moved since I last looked?" without looking. Equal fingerprints mean
        "nothing the dump renders has changed"; a different one means only "look
        again". It is computed from the database on every call, never stored, so
        writes from another process on the same sid are seen too — which is the
        reason it is a query and not an in-process write counter.

        WHAT IT MUST COVER, AND WHY EACH TERM IS THERE
        =============================================
        Every node writes at commit, so `count` plus `max(committed_at)` catches
        every structural or analytical addition — including an Estimation
        upsert, which deletes and re-creates (count unchanged, latest commit
        newer). Edges are counted separately because `GROUNDED_IN` is attached
        to an already-committed Decision and changes no node at all. The rest are
        the MUTABLE fields: the ones excluded from every hash precisely so they
        can change in place after commit, which means a count and a timestamp
        cannot see them. Each is folded in as the total length of its text over
        the scope, not as a count, so a value changing from one string to another
        (a validation verdict, a re-digested Input) still moves the fingerprint:
        `discarded`, `validation`, `digest`, the Statement's cosmetic
        `display_text` override (`concerns/display_text_edit.py`), and the
        Transition trio `instruction`/`summary`/`haiku`. `saved_at` is included
        because a save of a committed node is what every one of those mutations
        does.

        Adding a mutable field to a node without adding it here makes the
        Advisor's render cache serve a stale prompt for exactly the turns that
        changed that field — `tests/test_context_render_cache.py` lists the
        mutable fields it knows and fails when a node declares one it does not.

        Returns None when there is no scope, so a caller treats "cannot tell" as
        "look again" rather than as "nothing changed".
        """
        if not sid:
            return None

        nodes_query = """
        MATCH (n:Node {sid: $sid})
        RETURN count(n) AS nodes,
               max(n.committed_at) AS latest_commit,
               max(n.saved_at) AS latest_save,
               sum(size(coalesce(n.discarded, ''))) AS discarded_chars,
               sum(size(coalesce(n.validation, ''))) AS validation_chars,
               sum(size(coalesce(n.digest, ''))) AS digest_chars,
               sum(size(coalesce(n.display_text, ''))) AS display_text_chars,
               sum(size(coalesce(n.instruction, ''))) AS instruction_chars,
               sum(size(coalesce(n.summary, ''))) AS summary_chars,
               sum(size(coalesce(n.haiku, ''))) AS haiku_chars
        """
        edges_query = """
        MATCH (n:Node {sid: $sid})-[r]->()
        RETURN count(r) AS edges
        """
        nodes = list(graph_db.execute_and_fetch(nodes_query, {"sid": sid}))[0]
        edges = list(graph_db.execute_and_fetch(edges_query, {"sid": sid}))[0]
        return (
            nodes["nodes"],
            str(nodes["latest_commit"]),
            str(nodes["latest_save"]),
            nodes["discarded_chars"],
            nodes["validation_chars"],
            nodes["digest_chars"],
            nodes["display_text_chars"],
            nodes["instruction_chars"],
            nodes["summary_chars"],
            nodes["haiku_chars"],
            edges["edges"],
        )

