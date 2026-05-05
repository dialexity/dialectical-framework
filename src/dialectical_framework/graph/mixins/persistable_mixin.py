"""
Marker class for mixins whose fields should be persisted to the graph database.

GQLAlchemy's NodeMetaclass only collects fields from the Node inheritance chain.
By marking mixins with PersistableMixin and using MixinAwareNodeMeta on BaseNode,
fields defined in mixins will be properly persisted.
"""

from __future__ import annotations


class PersistableMixin:
    """
    Marker base class for mixins whose fields should be persisted to the graph database.

    Example:
        class IntentMixin(PersistableMixin):
            intent: Optional[str] = None

        class MyNode(IntentMixin, BaseNode):
            pass  # intent field will be persisted
    """
