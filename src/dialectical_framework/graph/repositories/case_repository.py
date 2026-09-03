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

