"""
Base classes for relationship layer classification.

The Dialectical Framework has two main relationship layers:

1. **ImmutableStructure** - The structural layer that forms the immutable
   reasoning framework from DialecticalComponents to Wheels. Has two sub-types:

   a) **IdentityRelationship** - Defines what a node IS:
      - IS_SOURCE_OF, IS_TARGET_OF: Define Transition's identity
      - Polarity (T, A, T+, T-, A+, A-): Define WisdomUnit's identity
      Blocked if SOURCE node is committed.

   b) **ContainerMembership** - Defines container composition:
      - BELONGS_TO_NEXUS: WisdomUnit → Nexus
      - BELONGS_TO_CYCLE: Transition → Cycle/Wheel/Spiral/Transformation
      - HAS_CYCLE: Nexus → Cycle
      - HAS_WHEEL: Cycle → Wheel
      Blocked if TARGET (container) is committed.
      Committed children can be added to uncommitted containers.

2. **AnalyticalStructure** - The analytical layer that attaches
   insights to the immutable structure:
   - Transformations, Spirals, Syntheses
   - Rationales explaining assessable entities
   - Estimations scoring entities
   - Audit chains (critiques)

   These artifacts can be DETACHED/REMOVED without compromising the
   structural layer's hash integrity. The "analytical" designation means
   these relationships are not part of the structural Merkle tree.

   Note: Analytical containers (Transformation, Spiral) still follow
   IncrementalBuildMixin rules - once committed, no new members.

Both layers can be exported/imported independently while maintaining integrity.
"""
from __future__ import annotations

from gqlalchemy import Relationship


class ImmutableStructure(Relationship):
    """
    Base marker for structural layer relationships.

    These relationships form the immutable reasoning framework.
    Use subclasses IdentityRelationship or ContainerMembership
    for proper validation behavior.
    """

    pass


class IdentityRelationship(ImmutableStructure):
    """
    Structural relationship that defines a node's identity.

    Examples:
    - IS_SOURCE_OF, IS_TARGET_OF: Define what a Transition represents
    - Polarity (T, A, etc.): Define what a WisdomUnit contains

    Validation: Blocked if the SOURCE node is committed, because
    changing identity relationships would change the node's hash.
    """

    pass


class ContainerMembership(ImmutableStructure):
    """
    Structural relationship for container composition (incoming edges).

    Use for BELONGS_TO_* relationships where children point TO containers:
    - BELONGS_TO_NEXUS: WisdomUnit → Nexus
    - BELONGS_TO_CYCLE: Transition → Cycle/Wheel/Spiral/Transformation

    Validation: Blocked if the TARGET (container) is committed.
    Committed children CAN be added to uncommitted containers,
    because the child's hash doesn't include container membership.
    """

    pass


class OutgoingContainerMembership(ImmutableStructure):
    """
    Structural relationship for container composition (outgoing edges).

    Use for HAS_* relationships where containers point TO children:
    - HAS_STATEMENT: Ideas → DialecticalComponent

    Validation: Blocked if the SOURCE (container) is committed.
    This is the inverse of ContainerMembership - used when the container
    owns the outgoing edge rather than receiving incoming edges.
    """

    pass


class AnalyticalStructure(Relationship):
    """
    Marker for analytical layer relationships.

    These relationships attach analytical artifacts to the structure:
    - Transformations and Spirals (reasoning through tensions)
    - Rationales and Estimations (explanations and scores)
    - Syntheses (emergent insights)

    "Analytical" means these relationships can be DETACHED/REMOVED
    without compromising the structural layer's hash consistency.
    The structure remains stable while analysis evolves.

    Note: Analytical containers still follow IncrementalBuildMixin
    commit rules - once committed, they cannot accept new members.
    """

    pass
