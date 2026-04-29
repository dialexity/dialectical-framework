"""Relationship model for statement provenance."""
from __future__ import annotations

from dialectical_framework.graph.relationships.immutable_structure import (
    OutgoingContainerMembership,
)


class HasStatementRelationship(OutgoingContainerMembership, type="HAS_STATEMENT"):
    """
    Links a node to its extracted Statements.

    Used by Ideas, Input, and Transition to connect to vocabulary-grade Statements.

    OutgoingContainerMembership blocking only applies to IncrementalBuildMixin
    containers (Ideas). For Input and Transition, statements can be added after
    commit since their hashes don't include statements.
    """

    pass
