"""
Mixin providing forking capabilities for reasoning foundation nodes.

ForkableMixin enables lineage tracking (origin_hash) and branch labeling
for nodes that represent forking points in dialectical reasoning.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from dialectical_framework.graph.mixins.persistable_mixin import PersistableMixin

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.base_node import BaseNode


class ForkableMixin(PersistableMixin):
    """
    Mixin for forking points (WisdomUnit, Nexus).

    Provides:
    - origin_hash: Lineage tracking (parent's hash when forked)
    - branch: Mutable label for the fork tip (like git refs)

    Forking points are the reasoning foundations that can be explored
    in alternative ways. When you fork a WisdomUnit or Nexus, the new
    node gets origin_hash set to the source's hash, creating a lineage chain.

    Branch is mutable metadata that doesn't affect hash computation.
    It acts as a pointer to identify the tip of a lineage chain.
    Branch names can be hierarchical: "main", "main/feature", "main/feature/sub".

    Used by: WisdomUnit, Nexus

    Example:
        # Fork a WisdomUnit to explore different framing
        forked_wu = wu.clone(branch="main")
        forked_wu.t_plus.disconnect(old_component)
        forked_wu.t_plus.connect(new_component)
        forked_wu.commit()

        # Extend the branch
        next_wu = forked_wu.clone()
        # ... modify ...
        next_wu.commit()
        forked_wu.move_branch_to(next_wu)  # Move branch pointer to new tip
    """

    origin_hash: Optional[str] = None
    branch: Optional[str] = None

    def move_branch_to(self, target: ForkableMixin) -> None:
        """
        Move branch pointer from this node to target node.

        Like `git checkout -B <branch>` - moves the branch ref to a new tip.
        Both nodes must be committed for this operation.

        Args:
            target: The new tip node (must be forkable and committed)

        Raises:
            TypeError: If self or target is not a BaseNode subclass
            ValueError: If target is not committed or this node has no branch

        Example:
            # Extend a branch
            new_wu = old_wu.clone()
            new_wu.commit()
            old_wu.move_branch_to(new_wu)  # "main" now points to new_wu
        """
        # Runtime import to avoid circular dependency
        from dialectical_framework.graph.nodes.base_node import BaseNode

        if not isinstance(self, BaseNode):
            raise TypeError("ForkableMixin must be used with BaseNode subclass")
        if not isinstance(target, BaseNode):
            raise TypeError("Target must be a BaseNode subclass")

        if not target.is_committed:
            raise ValueError("Target must be committed")
        if self.branch is None:
            raise ValueError("This node has no branch to move")

        target.branch = self.branch
        target.save()

        self.branch = None
        self.save()
