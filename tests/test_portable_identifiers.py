"""
Tests for the portable identifier system: uid, sid, origin_uid, nid.

These tests verify the identifier model described in docs/portability.md:
- sid (scope ID): Brainstorm's uid propagates to all descendants
- origin_uid (lineage ID): Preserved across clones for provenance tracking
- nid (portable address): <sid>:<uid> or <sid> for Brainstorm
"""

from __future__ import annotations

import pytest

from dialectical_framework.graph.nodes.base_node import BaseNode
from dialectical_framework.graph.nodes.brainstorm import Brainstorm
from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
from dialectical_framework.graph.nodes.ideas import Ideas
from dialectical_framework.graph.nodes.input import Input
from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit
from dialectical_framework.graph.scope_context import ScopeContext


class TestScopeContext:
    """Tests for the ScopeContext service."""

    def test_default_scope_is_none(self):
        """Default scope should be None."""
        ctx = ScopeContext()
        assert ctx.get_current_scope() is None

    def test_context_manager_sets_scope(self):
        """Context manager should set scope within the block."""
        ctx = ScopeContext()
        test_sid = "test-scope-123"

        with ctx.scope(test_sid):
            assert ctx.get_current_scope() == test_sid

        # After exiting, scope should be restored to None
        assert ctx.get_current_scope() is None

    def test_nested_scopes(self):
        """Nested context managers should work correctly."""
        ctx = ScopeContext()

        with ctx.scope("outer"):
            assert ctx.get_current_scope() == "outer"

            with ctx.scope("inner"):
                assert ctx.get_current_scope() == "inner"

            # After exiting inner, should be back to outer
            assert ctx.get_current_scope() == "outer"

        # After exiting outer, should be None
        assert ctx.get_current_scope() is None

    def test_set_and_reset(self):
        """Direct set/reset via token should work."""
        ctx = ScopeContext()

        token = ctx.set_current_scope("test-sid")
        assert ctx.get_current_scope() == "test-sid"

        # Reset via contextvars directly
        import contextvars
        from dialectical_framework.graph.scope_context import _current_scope
        _current_scope.reset(token)

        assert ctx.get_current_scope() is None


class TestBrainstormIdentifiers:
    """Tests for Brainstorm as scope root."""

    def test_brainstorm_is_own_scope(self):
        """Brainstorm should have sid == uid."""
        brainstorm = Brainstorm()
        brainstorm.save()

        assert brainstorm.sid == brainstorm.uid

    def test_brainstorm_nid_equals_sid(self):
        """Brainstorm nid should equal sid (no :uid suffix)."""
        brainstorm = Brainstorm()
        brainstorm.save()

        assert brainstorm.nid == brainstorm.sid
        assert ":" not in brainstorm.nid  # No separator for scope root

    def test_brainstorm_origin_uid_equals_uid(self):
        """New Brainstorm should have origin_uid == uid."""
        brainstorm = Brainstorm()
        brainstorm.save()

        assert brainstorm.origin_uid == brainstorm.uid


class TestNodeIdentifierInheritance:
    """Tests for sid inheritance via ScopeContext."""

    def test_input_inherits_sid_from_context(self):
        """Input created within scope context should inherit sid."""
        brainstorm = Brainstorm()
        brainstorm.save()

        ctx = ScopeContext()
        with ctx.scope(brainstorm.uid):
            input_node = Input(content="https://example.com")
            input_node.save()

        assert input_node.sid == brainstorm.uid

    def test_input_nid_format(self):
        """Input nid should be <sid>:<uid>."""
        brainstorm = Brainstorm()
        brainstorm.save()

        ctx = ScopeContext()
        with ctx.scope(brainstorm.uid):
            input_node = Input(content="https://example.com")
            input_node.save()

        expected_nid = f"{brainstorm.uid}:{input_node.uid}"
        assert input_node.nid == expected_nid

    def test_component_inherits_sid_from_context(self):
        """Component created within scope context should inherit sid."""
        brainstorm = Brainstorm()
        brainstorm.save()

        ctx = ScopeContext()
        with ctx.scope(brainstorm.uid):
            comp = DialecticalComponent(statement="Test statement")
            comp.save()

        assert comp.sid == brainstorm.uid
        assert comp.nid == f"{brainstorm.uid}:{comp.uid}"

    def test_ideas_inherits_sid_from_context(self):
        """Ideas created within scope context should inherit sid."""
        brainstorm = Brainstorm()
        brainstorm.save()

        ctx = ScopeContext()
        with ctx.scope(brainstorm.uid):
            ideas = Ideas(intent="Test extraction")
            ideas.save()

        assert ideas.sid == brainstorm.uid

    def test_origin_uid_set_for_new_nodes(self):
        """New nodes should have origin_uid == uid."""
        brainstorm = Brainstorm()
        brainstorm.save()

        ctx = ScopeContext()
        with ctx.scope(brainstorm.uid):
            comp = DialecticalComponent(statement="Test")
            comp.save()

        assert comp.origin_uid == comp.uid

    def test_explicit_sid_overrides_context(self):
        """Explicit sid parameter should override context."""
        brainstorm1 = Brainstorm()
        brainstorm1.save()

        brainstorm2 = Brainstorm()
        brainstorm2.save()

        ctx = ScopeContext()
        with ctx.scope(brainstorm1.uid):
            # Explicit sid takes precedence
            comp = DialecticalComponent(statement="Test", sid=brainstorm2.uid)
            comp.save()

        assert comp.sid == brainstorm2.uid


class TestOrphanNodes:
    """Tests for nodes created without scope context."""

    def test_node_without_context_has_no_sid(self):
        """Node created without scope context should have sid=None."""
        comp = DialecticalComponent(statement="Orphan")
        comp.save()

        assert comp.sid is None

    def test_orphan_node_nid_fallback_to_uid(self):
        """Orphan node nid should fall back to just uid."""
        comp = DialecticalComponent(statement="Orphan")
        comp.save()

        assert comp.nid == comp.uid


class TestCloneOperation:
    """Tests for the clone operation."""

    def test_clone_generates_new_uid(self):
        """Cloned node should have a new uid."""
        brainstorm1 = Brainstorm()
        brainstorm1.save()

        brainstorm2 = Brainstorm()
        brainstorm2.save()

        ctx = ScopeContext()
        with ctx.scope(brainstorm1.uid):
            original = DialecticalComponent(statement="Original statement")
            original.save()

        cloned = original.clone(destination_sid=brainstorm2.uid)

        assert cloned.uid != original.uid

    def test_clone_sets_new_sid(self):
        """Cloned node should have the destination sid."""
        brainstorm1 = Brainstorm()
        brainstorm1.save()

        brainstorm2 = Brainstorm()
        brainstorm2.save()

        ctx = ScopeContext()
        with ctx.scope(brainstorm1.uid):
            original = DialecticalComponent(statement="Original")
            original.save()

        cloned = original.clone(destination_sid=brainstorm2.uid)
        cloned.save()

        assert cloned.sid == brainstorm2.uid

    def test_clone_preserves_origin_uid(self):
        """Cloned node should preserve origin_uid for lineage tracking."""
        brainstorm1 = Brainstorm()
        brainstorm1.save()

        brainstorm2 = Brainstorm()
        brainstorm2.save()

        ctx = ScopeContext()
        with ctx.scope(brainstorm1.uid):
            original = DialecticalComponent(statement="Original")
            original.save()

        cloned = original.clone(destination_sid=brainstorm2.uid)

        # origin_uid should trace back to the original
        assert cloned.origin_uid == original.uid

    def test_clone_chain_preserves_original_origin(self):
        """Chained clones should all trace back to original origin_uid."""
        brainstorm1 = Brainstorm()
        brainstorm1.save()

        brainstorm2 = Brainstorm()
        brainstorm2.save()

        brainstorm3 = Brainstorm()
        brainstorm3.save()

        ctx = ScopeContext()
        with ctx.scope(brainstorm1.uid):
            original = DialecticalComponent(statement="Original")
            original.save()

        # First clone
        clone1 = original.clone(destination_sid=brainstorm2.uid)
        clone1.save()

        # Second clone (from the first clone)
        clone2 = clone1.clone(destination_sid=brainstorm3.uid)
        clone2.save()

        # All should trace back to original
        assert original.origin_uid == original.uid
        assert clone1.origin_uid == original.uid
        assert clone2.origin_uid == original.uid  # Still original, not clone1

    def test_clone_copies_content_fields(self):
        """Cloned node should copy content fields."""
        brainstorm1 = Brainstorm()
        brainstorm1.save()

        brainstorm2 = Brainstorm()
        brainstorm2.save()

        ctx = ScopeContext()
        with ctx.scope(brainstorm1.uid):
            original = DialecticalComponent(
                statement="Test statement",
                handle="test-handle"
            )
            original.save()

        cloned = original.clone(destination_sid=brainstorm2.uid)

        assert cloned.statement == original.statement
        assert cloned.handle == original.handle

    def test_clone_computes_new_nid(self):
        """Cloned node should have nid computed from new sid:uid."""
        brainstorm1 = Brainstorm()
        brainstorm1.save()

        brainstorm2 = Brainstorm()
        brainstorm2.save()

        ctx = ScopeContext()
        with ctx.scope(brainstorm1.uid):
            original = DialecticalComponent(statement="Original")
            original.save()

        cloned = original.clone(destination_sid=brainstorm2.uid)
        cloned.save()

        expected_nid = f"{brainstorm2.uid}:{cloned.uid}"
        assert cloned.nid == expected_nid


class TestScopeValidationOnConnect:
    """Tests for scope validation when connecting nodes."""

    def test_same_scope_connection_allowed(self):
        """Nodes from the same scope should connect successfully."""
        brainstorm = Brainstorm()
        brainstorm.save()

        ctx = ScopeContext()
        with ctx.scope(brainstorm.uid):
            input_node = Input(content="https://example.com")
            input_node.save()

        # Connect Input to its Brainstorm (same scope)
        brainstorm.inputs.connect(input_node)

        assert brainstorm.inputs.count() == 1

    def test_different_scope_connection_raises_error(self):
        """Nodes from different scopes should raise ValueError on connect."""
        brainstorm1 = Brainstorm()
        brainstorm1.save()

        brainstorm2 = Brainstorm()
        brainstorm2.save()

        ctx = ScopeContext()
        with ctx.scope(brainstorm2.uid):
            input_node = Input(content="https://example.com")
            input_node.save()

        # Try to connect Input (scope2) to Brainstorm1 (scope1)
        with pytest.raises(ValueError) as exc_info:
            brainstorm1.inputs.connect(input_node)

        assert "different scopes" in str(exc_info.value).lower()

    def test_orphan_node_connection_allowed(self):
        """Orphan nodes (sid=None) should be connectable to any scope."""
        brainstorm = Brainstorm()
        brainstorm.save()

        # Create Input without scope context
        input_node = Input(content="https://example.com")
        input_node.save()

        assert input_node.sid is None

        # Should be able to connect to brainstorm
        brainstorm.inputs.connect(input_node)
        assert brainstorm.inputs.count() == 1


class TestIntegration:
    """Integration tests for full workflow with identifiers."""

    def test_full_brainstorm_workflow_with_identifiers(self):
        """Test complete workflow from Brainstorm to components with identifiers."""
        # Create brainstorm (scope root)
        brainstorm = Brainstorm(intent="Test workflow")
        brainstorm.save()

        assert brainstorm.sid == brainstorm.uid
        assert brainstorm.nid == brainstorm.sid

        ctx = ScopeContext()
        with ctx.scope(brainstorm.uid):
            # Create Input
            input_node = Input(content="https://example.com")
            input_node.save()

            assert input_node.sid == brainstorm.uid
            assert input_node.nid == f"{brainstorm.uid}:{input_node.uid}"

            # Create Ideas
            ideas = Ideas(intent="Extract claims")
            ideas.save()

            # Create Component
            comp = DialecticalComponent(statement="Test statement")
            comp.save()

        # Connect them
        brainstorm.inputs.connect(input_node)
        input_node.ideas.connect(ideas)
        ideas.statements.connect(comp)

        # Verify all have same scope
        assert input_node.sid == brainstorm.uid
        assert ideas.sid == brainstorm.uid
        assert comp.sid == brainstorm.uid

        # Verify vocabulary
        vocab = brainstorm.get_vocabulary()
        assert comp in vocab
