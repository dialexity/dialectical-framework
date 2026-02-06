"""Relationship model for statement provenance."""
from __future__ import annotations

from dialectical_framework.graph.relationships.immutable_structure import (
    OutgoingContainerMembership,
)


class HasStatementRelationship(OutgoingContainerMembership, type="HAS_STATEMENT"):
    """
    Links Ideas to extracted DialecticalComponents.

    OutgoingContainerMembership: Blocked if the SOURCE (Ideas container) is committed.
    Statements must be connected before Ideas.commit().

    Note: Input also uses this relationship but Input is not an IncrementalBuildMixin
    container - its hash doesn't include statements. The validation only affects
    Ideas (which is a container). For Input, statements can be added after commit
    because Input.statements uses the same relationship type but Input's is_committed
    doesn't trigger the blocking behavior since Input's hash is content-only.
    """

    pass
