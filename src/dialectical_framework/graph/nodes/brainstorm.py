"""
Brainstorm node for the dialectical framework.

Brainstorm is a portable discovery artifact that groups Inputs and their Ideas,
providing a vocabulary of components for downstream dialectical analysis.
"""

from __future__ import annotations

import uuid
from typing import Any, ClassVar, Union, TYPE_CHECKING, Self

from dependency_injector.wiring import Provide, inject
from gqlalchemy import Memgraph, Neo4j

from dialectical_framework.enums.di import DI
from dialectical_framework.graph.nodes.base_node import BaseNode
from dialectical_framework.graph.relationship_manager import (
    RelationshipFrom,
    RelationshipTo,
    RelationshipManager,
)
from dialectical_framework.graph.relationships.has_input_relationship import (
    HasInputRelationship,
)

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.input import Input


class Brainstorm(BaseNode, label="Brainstorm"):
    """
    A portable discovery artifact grouping Inputs and Ideas.

    Brainstorm serves as the entry point for dialectical analysis, collecting
    Input sources and providing a unified vocabulary of components extracted
    from those inputs via Ideas.

    Note: Brainstorm does not have intent - the intent about what to explore
    is "outside the system" and belongs to the user/context, not the artifact.

    Graph structure:
        Brainstorm
        ├──[HAS_INPUT]──► Input ──[HAS_STATEMENT]──► DialecticalComponent
        │                   │
        │                   └──[DISTILLED_TO]──► Ideas ──[HAS_STATEMENT]──► DialecticalComponent
        │
        └── Vocabulary = all Components via HAS_STATEMENT paths

    Relationships:
    - Brainstorm has one or more Inputs (via HAS_INPUT)
    - Each Input can have Ideas extracted from it
    - Vocabulary includes all components reachable via HAS_STATEMENT

    Nexuses (explorations) reference this Brainstorm via sid field.

    Example:
        from dialectical_framework.graph.repositories.dialectical_component_repository import (
            DialecticalComponentRepository
        )

        brainstorm = Brainstorm()
        brainstorm.commit()

        input_node = Input(content="https://article.com")
        input_node.commit()
        brainstorm.inputs.connect(input_node)

        ideas = Ideas(intent="Extract productivity claims")
        ideas.commit()
        input_node.ideas.connect(ideas)

        comp = DialecticalComponent(statement="Remote work improves focus")
        comp.commit()
        ideas.statements.connect(comp)

        # Vocabulary includes all components in scope
        from dialectical_framework.graph.scope_context import scope
        repo = DialecticalComponentRepository()
        with scope(brainstorm.sid):
            vocab = repo.get_vocabulary()
        assert comp in vocab
    """

    # Input sources (required - at least one Input)
    inputs: ClassVar[RelationshipManager[Input]] = RelationshipTo(
        "Input",
        model=HasInputRelationship,
        cardinality=(1, None),  # At least one Input required
    )

    def __init__(self, **data: Any) -> None:
        """
        Initialize a Brainstorm.

        Brainstorm is a scope root. It generates a UUID for sid on creation,
        which serves as the scope identifier for all children.

        Args:
            **data: Field values for the brainstorm
        """
        # Generate UUID for sid if not provided - this IS the scope identity
        if "sid" not in data or data["sid"] is None:
            data["sid"] = str(uuid.uuid4())
        super().__init__(**data)

    @property
    def is_committed(self) -> bool:
        """Check if this Brainstorm has been saved (has database _id)."""
        return self._id is not None

    @inject
    def commit(
        self,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> Self:
        """
        Commit this Brainstorm to the database.

        Brainstorm is a scope root with UUID-based identity (sid).
        It never computes a hash - hash remains None.

        Returns:
            Self for chaining
        """
        result = graph_db.save_node(self)
        if result is not None and result._id is not None:
            self._id = result._id
        return self

    def __repr__(self) -> str:
        """String representation of the brainstorm."""
        input_count = self.inputs.count()
        sid_str = self.sid[:8] if self.sid else "no-sid"
        return f"Brainstorm({sid_str}, inputs={input_count})"

    def __str__(self) -> str:
        """Human-readable string representation."""
        from dialectical_framework.graph.repositories.dialectical_component_repository import (
            DialecticalComponentRepository
        )

        input_count = self.inputs.count()
        repo = DialecticalComponentRepository()
        with self:
            vocab_count = len(repo.get_vocabulary())
        return f"Brainstorm ({input_count} inputs, {vocab_count} components)"

    def __enter__(self) -> Self:
        """Enter scope context for this brainstorm."""
        from dialectical_framework.graph.scope_context import scope
        self._scope_cm = scope(self.sid)
        self._scope_cm.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit scope context."""
        if hasattr(self, '_scope_cm'):
            self._scope_cm.__exit__(exc_type, exc_val, exc_tb)
