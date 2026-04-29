"""
Tests for the Merkle identity system: hash, origin_hash, sid.

These tests verify the identifier model:
- hash (primary identity): sha256 of node's structure + origin_hash
- origin_hash (lineage ID): Parent's hash, preserved across clones
- sid (scope ID): Case's hash propagates to all descendants
"""

from __future__ import annotations

import pytest

from dialectical_framework.graph.nodes.base_node import ImmutableNodeError
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.nodes.ideas import Ideas
from dialectical_framework.graph.nodes.input import Input
from dialectical_framework.graph.nodes.polarity import Polarity
from dialectical_framework.graph.nodes.perspective import Perspective
from dialectical_framework.graph.relationships.polarity_relationship import (
    HasPolarityRelationship, TPlusRelationship, TMinusRelationship,
    APlusRelationship, AMinusRelationship,
)
from dialectical_framework.graph.scope_context import scope, get_current_sid
from dialectical_framework.graph.repositories.statement_repository import (
    StatementRepository
)


def _create_complete_pp(
    t, a, t_plus, t_minus, a_plus, a_minus, intent=None
) -> Perspective:
    """Helper: create a complete Perspective with Polarity and all aspects."""
    polarity = Polarity(intent=intent)
    polarity.set_t(t, heuristic_similarity=1.0)
    polarity.set_a(a, heuristic_similarity=0.8)
    polarity.commit()

    pp = Perspective(intent=intent)
    pp.save()
    pp.polarity.connect(polarity, relationship=HasPolarityRelationship())
    pp.t_plus.connect(t_plus, relationship=TPlusRelationship(alias="T+", heuristic_similarity=0.9))
    pp.t_minus.connect(t_minus, relationship=TMinusRelationship(alias="T-", heuristic_similarity=0.9))
    pp.a_plus.connect(a_plus, relationship=APlusRelationship(alias="A+", heuristic_similarity=0.9))
    pp.a_minus.connect(a_minus, relationship=AMinusRelationship(alias="A-", heuristic_similarity=0.9))
    return pp


class TestScopeContext:
    """Tests for the scope context functions."""

    def test_default_scope_is_none(self):
        """Default scope should be None."""
        assert get_current_sid() is None

    def test_context_manager_sets_scope(self):
        """Context manager should set scope within the block."""
        test_sid = "test-scope-123"

        with scope(test_sid):
            assert get_current_sid() == test_sid

        # After exiting, scope should be restored to None
        assert get_current_sid() is None

    def test_nested_scopes(self):
        """Nested context managers should work correctly."""
        with scope("outer"):
            assert get_current_sid() == "outer"

            with scope("inner"):
                assert get_current_sid() == "inner"

            # After exiting inner, should be back to outer
            assert get_current_sid() == "outer"

        # After exiting outer, should be None
        assert get_current_sid() is None


class TestCommitWorkflow:
    """Tests for the commit() workflow (like git commit)."""

    def test_node_starts_in_draft_state(self):
        """New node should start uncommitted (draft state)."""
        comp = Statement(text="Test statement for draft", meaning="test")

        assert not comp.is_committed
        assert comp.hash is None

    def test_save_computes_hash(self):
        """save() should compute hash."""
        import random
        comp = Statement(text=f"Test statement {random.random()}", meaning="test")
        comp.commit()

        assert comp.is_committed
        assert comp.hash is not None
        assert len(comp.hash) == 64  # sha256 hex

    def test_save_is_immutable(self):
        """Calling save() on saved node should raise ImmutableNodeError."""
        import random
        from dialectical_framework.graph.nodes.base_node import ImmutableNodeError
        comp = Statement(text=f"Test statement {random.random()}", meaning="test")
        comp.commit()
        first_hash = comp.hash

        # Second save should raise ImmutableNodeError (node is immutable after save)
        with pytest.raises(ImmutableNodeError):
            comp.commit()

        # Hash should remain unchanged
        assert comp.hash == first_hash

    def test_hash_before_save(self):
        """hash should be None before save."""
        comp = Statement(text="Test", meaning="test")

        # Before save: hash is None
        assert comp.hash is None
        assert not comp.is_committed

    def test_hash_after_save(self):
        """hash should be set after save."""
        comp = Statement(text="Test", meaning="test")
        comp.commit()

        # After save: hash is set
        assert comp.hash is not None
        assert comp.is_committed
        assert len(comp.hash) == 64  # sha256 hex

    def test_save_workflow(self):
        """Standard workflow: create -> save (computes hash and persists)."""
        comp = Statement(text="Test", meaning="test")
        comp.commit()

        assert comp._id is not None
        assert comp.hash is not None

    def test_hash_deterministic(self):
        """Same content should produce same hash (without saving both - would violate unique constraint)."""
        import random
        unique_content = f"Same content {random.random()}"
        comp1 = Statement(text=unique_content, meaning="test")
        comp2 = Statement(text=unique_content, meaning="test")

        # Compute hashes without saving (to test determinism without unique constraint issue)
        hash1 = comp1.compute_hash()
        hash2 = comp2.compute_hash()

        assert hash1 == hash2

        # Also verify by saving one - the saved hash should match
        comp1.commit()
        assert comp1.hash == hash1


class TestCaseIdentifiers:
    """Tests for Case as scope root."""

    def test_case_has_uuid_sid_on_creation(self):
        """Case generates UUID for sid on creation."""
        case_node = Case()

        # sid is set immediately (UUID)
        assert case_node.sid is not None
        assert len(case_node.sid) == 36  # UUID format

    def test_case_workflow(self):
        """Full Case workflow: create -> commit (sid already set)."""
        case_node = Case()
        case_node.commit()

        # sid is UUID, hash is None (Case never commits)
        assert case_node.sid is not None
        assert case_node.hash is None


class TestNodeIdentifierInheritance:
    """Tests for sid inheritance via scope context."""

    def test_input_inherits_sid_from_context(self):
        """Input created within scope context should inherit sid."""
        import random
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            input_node = Input(content=f"https://example.com/{random.random()}")
            input_node.commit()

        assert input_node.sid == case_node.sid

    def test_component_inherits_sid_from_context(self):
        """Component created within scope context should inherit sid."""
        case_node = Case()
        case_node.commit()

        import random
        with scope(case_node.sid):
            comp = Statement(text=f"Test statement {random.random()}", meaning="test")
            comp.commit()

        assert comp.sid == case_node.sid

    def test_ideas_inherits_sid_from_context(self):
        """Ideas created within scope context should inherit sid."""
        import random
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            ideas = Ideas(intent=f"Test extraction {random.random()}")
            ideas.save()
            ideas.commit()

        assert ideas.sid == case_node.sid

    def test_explicit_sid_overrides_context(self):
        """Explicit sid parameter should override context."""
        import random
        case_node1 = Case()
        case_node1.commit()

        case_node2 = Case()
        case_node2.commit()

        with scope(case_node1.sid):
            # Explicit sid takes precedence
            comp = Statement(text=f"Test {random.random()}", sid=case_node2.sid, meaning="test")
            comp.commit()

        assert comp.sid == case_node2.sid


class TestOrphanNodes:
    """Tests for nodes created without scope context."""

    def test_node_without_context_has_no_sid(self):
        """Node created without scope context should have sid=None."""
        import random
        comp = Statement(text=f"Orphan {random.random()}", meaning="test")
        comp.commit()

        assert comp.sid is None


class TestCloneOperation:
    """Tests for the clone operation.

    Important: Clone behavior differs between node categories:
    - Atoms (Statement, Input, etc.): Content-addressable, NO origin_hash.
      Same content = same hash regardless of cloning.
    - Forking Points (Perspective, Nexus): Have origin_hash for lineage tracking.
      Clones get different hashes due to origin_hash in computation.
    """

    def test_atom_clone_has_same_hash(self):
        """Cloned atom (Statement) should have same hash - content-addressable."""
        import random
        case_node1 = Case()
        case_node1.commit()

        case_node2 = Case()
        case_node2.commit()

        with scope(case_node1.sid):
            original = Statement(text=f"Original statement {random.random()}", meaning="test")
            original.commit()

        cloned = original.clone(destination_sid=case_node2.sid)
        cloned.commit()

        # Atoms are content-addressable: same content = same hash
        assert cloned.hash == original.hash

    def test_atom_clone_has_no_origin_hash(self):
        """Cloned atom should NOT have origin_hash - atoms don't track lineage."""
        import random
        case_node1 = Case()
        case_node1.commit()

        with scope(case_node1.sid):
            original = Statement(text=f"Original {random.random()}", meaning="test")
            original.commit()

        cloned = original.clone(destination_sid=case_node1.sid)

        # Atoms don't have origin_hash attribute (not ForkableMixin)
        assert not hasattr(cloned, 'origin_hash') or cloned.origin_hash is None

    def test_clone_sets_new_sid(self):
        """Cloned node should have the destination sid."""
        import random
        case_node1 = Case()
        case_node1.commit()

        case_node2 = Case()
        case_node2.commit()

        with scope(case_node1.sid):
            original = Statement(text=f"Original {random.random()}", meaning="test")
            original.commit()

        cloned = original.clone(destination_sid=case_node2.sid)
        cloned.commit()

        assert cloned.sid == case_node2.sid

    def test_forking_point_clone_sets_origin_hash(self):
        """Cloned forking point (Perspective) should have origin_hash pointing to original."""
        import random
        case_node1 = Case()
        case_node1.commit()

        case_node2 = Case()
        case_node2.commit()

        with scope(case_node1.sid):
            t = Statement(text=f"Thesis {random.random()}", meaning="test")
            t_plus = Statement(text=f"Thesis plus {random.random()}", meaning="test")
            t_minus = Statement(text=f"Thesis minus {random.random()}", meaning="test")
            a = Statement(text=f"Antithesis {random.random()}", meaning="test")
            a_plus = Statement(text=f"Antithesis plus {random.random()}", meaning="test")
            a_minus = Statement(text=f"Antithesis minus {random.random()}", meaning="test")
            for comp in [t, t_plus, t_minus, a, a_plus, a_minus]:
                comp.commit()

            original_pp = _create_complete_pp(t, a, t_plus, t_minus, a_plus, a_minus)
            original_pp.commit()

        cloned_pp = original_pp.clone(destination_sid=case_node2.sid)

        # Forking points have origin_hash pointing to source
        assert cloned_pp.origin_hash == original_pp.hash

    def test_forking_point_clone_has_different_hash(self):
        """Cloned forking point should have different hash due to origin_hash."""
        import random
        case_node1 = Case()
        case_node1.commit()

        case_node2 = Case()
        case_node2.commit()

        # Create orphan components (sid=None) so they can be shared across scopes
        t = Statement(text=f"Thesis {random.random()}", meaning="test")
        t_plus = Statement(text=f"Thesis plus {random.random()}", meaning="test")
        t_minus = Statement(text=f"Thesis minus {random.random()}", meaning="test")
        a = Statement(text=f"Antithesis {random.random()}", meaning="test")
        a_plus = Statement(text=f"Antithesis plus {random.random()}", meaning="test")
        a_minus = Statement(text=f"Antithesis minus {random.random()}", meaning="test")
        for comp in [t, t_plus, t_minus, a, a_plus, a_minus]:
            comp.commit()

        with scope(case_node1.sid):
            original_pp = _create_complete_pp(t, a, t_plus, t_minus, a_plus, a_minus)
            original_pp.commit()

        # Clone and reconnect components (clone doesn't copy relationships)
        cloned_pp = original_pp.clone(destination_sid=case_node2.sid)
        # Reconnect Polarity and aspects for the clone
        polarity = Polarity()
        polarity.set_t(t, heuristic_similarity=1.0)
        polarity.set_a(a, heuristic_similarity=0.8)
        polarity.commit()
        cloned_pp.save()
        cloned_pp.polarity.connect(polarity, relationship=HasPolarityRelationship())
        cloned_pp.t_plus.connect(t_plus, relationship=TPlusRelationship(alias="T+", heuristic_similarity=0.9))
        cloned_pp.t_minus.connect(t_minus, relationship=TMinusRelationship(alias="T-", heuristic_similarity=0.9))
        cloned_pp.a_plus.connect(a_plus, relationship=APlusRelationship(alias="A+", heuristic_similarity=0.9))
        cloned_pp.a_minus.connect(a_minus, relationship=AMinusRelationship(alias="A-", heuristic_similarity=0.9))
        cloned_pp.commit()

        # Forking points have different hashes due to origin_hash in computation
        assert cloned_pp.hash != original_pp.hash
        assert cloned_pp.origin_hash == original_pp.hash

    def test_clone_returns_uncommitted_node(self):
        """Clone should return uncommitted (draft) node."""
        import random
        case_node1 = Case()
        case_node1.commit()

        with scope(case_node1.sid):
            original = Statement(text=f"Original {random.random()}", meaning="test")
            original.commit()

        cloned = original.clone(destination_sid=case_node1.sid)

        # Cloned node should be uncommitted
        assert not cloned.is_committed
        assert cloned.hash is None

    def test_clone_copies_content_fields(self):
        """Cloned node should copy content fields."""
        import random
        case_node1 = Case()
        case_node1.commit()

        case_node2 = Case()
        case_node2.commit()

        with scope(case_node1.sid):
            original = Statement(text=f"Test statement {random.random()}", meaning="test")
            original.commit()

        cloned = original.clone(destination_sid=case_node2.sid)

        assert cloned.text == original.text


class TestScopeValidationOnConnect:
    """Tests for scope validation when connecting nodes."""

    def test_same_scope_connection_allowed(self):
        """Nodes from the same scope should connect successfully."""
        import random
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            input_node = Input(content=f"https://example.com/{random.random()}")
            input_node.commit()

        # Connect Input to its Case (same scope)
        case_node.inputs.connect(input_node)

        assert case_node.inputs.count() == 1

    def test_different_scope_connection_raises_error(self):
        """Nodes from different scopes should raise ValueError on connect."""
        import random
        case_node1 = Case()
        case_node1.commit()

        case_node2 = Case()
        case_node2.commit()

        with scope(case_node2.sid):
            input_node = Input(content=f"https://example.com/{random.random()}")
            input_node.commit()

        # Try to connect Input (scope2) to Case1 (scope1)
        with pytest.raises(ValueError) as exc_info:
            case_node1.inputs.connect(input_node)

        assert "different scopes" in str(exc_info.value).lower()

    def test_orphan_node_connection_allowed(self):
        """Orphan nodes (sid=None) should be connectable to any scope."""
        import random
        case_node = Case()
        case_node.commit()

        # Create Input without scope context
        input_node = Input(content=f"https://example.com/{random.random()}")
        input_node.commit()

        assert input_node.sid is None

        # Should be able to connect to case
        case_node.inputs.connect(input_node)
        assert case_node.inputs.count() == 1


class TestHashLookup:
    """Tests for git-style hash prefix lookup."""

    def test_short_prefix_lookup(self):
        """Should find node by short hash prefix."""
        import random
        from dialectical_framework.graph.repositories.node_repository import NodeRepository

        comp = Statement(text=f"Test for prefix lookup {random.random()}", meaning="test")
        comp.commit()

        repo = NodeRepository()
        found = repo.find_by_hash(comp.hash[:7])

        assert found is not None
        assert found.hash == comp.hash

    def test_prefix_too_short_returns_none(self):
        """Prefix shorter than 7 chars should return None (no match)."""
        from dialectical_framework.graph.repositories.node_repository import NodeRepository

        repo = NodeRepository()
        result = repo.find_by_hash("abc")

        assert result is None

    def test_find_by_full_hash(self):
        """Should find node by full hash."""
        import random
        from dialectical_framework.graph.repositories.node_repository import NodeRepository

        comp = Statement(text=f"Test for full hash lookup {random.random()}", meaning="test")
        comp.commit()

        repo = NodeRepository()
        found = repo.find_by_hash(comp.hash)

        assert found is not None
        assert found.hash == comp.hash


class TestLineageTracking:
    """Tests for origin_hash lineage tracking.

    Note: origin_hash is only set on forking points (Perspective, Nexus).
    Atoms don't have lineage tracking - they're global facts.
    """

    def test_forking_point_has_origin_hash(self):
        """Cloned forking points (Perspective) should have origin_hash set."""
        import random
        from dialectical_framework.graph.nodes.perspective import Perspective

        case_node1 = Case()
        case_node1.commit()

        # Create orphan components (shared globally)
        t = Statement(text=f"Thesis {random.random()}", meaning="test")
        t_plus = Statement(text=f"Thesis plus {random.random()}", meaning="test")
        t_minus = Statement(text=f"Thesis minus {random.random()}", meaning="test")
        a = Statement(text=f"Antithesis {random.random()}", meaning="test")
        a_plus = Statement(text=f"Antithesis plus {random.random()}", meaning="test")
        a_minus = Statement(text=f"Antithesis minus {random.random()}", meaning="test")

        for comp in [t, t_plus, t_minus, a, a_plus, a_minus]:
            comp.commit()

        with scope(case_node1.sid):
            original_pp = _create_complete_pp(t, a, t_plus, t_minus, a_plus, a_minus, intent="original")
            original_pp.commit()

        # Original should have no origin_hash
        assert original_pp.origin_hash is None

        # Create fork
        clone = original_pp.clone(destination_sid=case_node1.sid)
        clone.intent = "fork"

        # Before commit, origin_hash should be set
        assert clone.origin_hash == original_pp.hash

        # After commit, origin_hash should still be set - reconnect Polarity and aspects
        polarity = Polarity(intent="fork")
        polarity.set_t(t, heuristic_similarity=1.0)
        polarity.set_a(a, heuristic_similarity=0.8)
        polarity.commit()
        clone.save()
        clone.polarity.connect(polarity, relationship=HasPolarityRelationship())
        clone.t_plus.connect(t_plus, relationship=TPlusRelationship(alias="T+", heuristic_similarity=0.9))
        clone.t_minus.connect(t_minus, relationship=TMinusRelationship(alias="T-", heuristic_similarity=0.9))
        clone.a_plus.connect(a_plus, relationship=APlusRelationship(alias="A+", heuristic_similarity=0.9))
        clone.a_minus.connect(a_minus, relationship=AMinusRelationship(alias="A-", heuristic_similarity=0.9))
        clone.commit()

        assert clone.origin_hash == original_pp.hash

        # Verify different hashes due to origin_hash
        assert clone.hash != original_pp.hash

    def test_atoms_have_no_lineage(self):
        """Atoms (Statement) should NOT have origin_hash after clone."""
        import random

        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            original = Statement(text=f"Original {random.random()}", meaning="test")
            original.commit()

        clone = original.clone(destination_sid=case_node.sid)
        clone.commit()

        # Atoms don't have origin_hash (ForkableMixin is not in inheritance)
        assert not hasattr(clone, 'origin_hash') or clone.origin_hash is None

        # Same content = same hash (content-addressable)
        assert clone.hash == original.hash


class TestIntegration:
    """Integration tests for full workflow with identifiers."""

    def test_full_case_workflow_with_uuid_scope(self):
        """Test complete workflow from Case to components with UUID scope."""
        import random
        # Create case (scope root with UUID)
        case_node = Case()
        case_node.commit()

        assert case_node.sid is not None
        assert len(case_node.sid) == 36  # UUID format
        assert case_node.hash is None  # Case never commits

        with scope(case_node.sid):
            # Create Input
            input_node = Input(content=f"https://example.com/{random.random()}")
            input_node.commit()

            assert input_node.sid == case_node.sid

            # Create Ideas (container - save first, commit after statements)
            ideas = Ideas(intent=f"Extract claims {random.random()}")
            ideas.save()

            # Create Component
            comp = Statement(text=f"Test statement {random.random()}", meaning="test")
            comp.commit()

            # Connect statements before commit
            ideas.statements.connect(comp)
            ideas.commit()

        # Connect container relationships
        case_node.inputs.connect(input_node)
        input_node.ideas.connect(ideas)

        # Verify all have same scope
        assert input_node.sid == case_node.sid
        assert ideas.sid == case_node.sid
        assert comp.sid == case_node.sid

        # Verify vocabulary
        repo = StatementRepository()
        with scope(case_node.sid):
            vocab = repo.get_vocabulary()
        assert comp in vocab


class TestHashIntegrityOnSave:
    """Tests for hash integrity verification when calling save() after commit."""

    def test_save_blocks_structural_modification_after_commit(self):
        """Verify save() raises ImmutableNodeError if structural fields modified after commit."""
        import random
        comp = Statement(text=f"Original statement {random.random()}", meaning="test")
        comp.commit()

        # Modify structural field
        comp.text = "Modified statement"

        # save() should raise ImmutableNodeError
        with pytest.raises(ImmutableNodeError) as exc_info:
            comp.save()
        assert "structural fields have been modified" in str(exc_info.value)

    def test_save_allows_metadata_modification_after_commit(self):
        """Verify save() allows metadata changes after commit."""
        import random
        comp = Statement(text=f"Test statement {random.random()}", meaning="test")
        comp.commit()
        original_hash = comp.hash

        # Modify metadata field
        comp.sid = "new-scope-id"

        # save() should succeed
        comp.save()

        # Hash should be unchanged
        assert comp.hash == original_hash

    def test_save_blocks_intent_modification_after_commit(self):
        """Verify save() raises ImmutableNodeError if intent modified after commit."""
        import random
        ideas = Ideas(intent=f"Original intent {random.random()}")
        ideas.save()
        ideas.commit()

        # Modify intent (structural field via IntentMixin)
        ideas.intent = "Modified intent"

        # save() should raise ImmutableNodeError
        with pytest.raises(ImmutableNodeError) as exc_info:
            ideas.save()
        assert "structural fields have been modified" in str(exc_info.value)

    def test_save_blocks_content_modification_on_input(self):
        """Verify save() raises ImmutableNodeError if Input content modified after commit."""
        import random
        input_node = Input(content=f"https://example.com/{random.random()}")
        input_node.commit()

        # Modify structural field
        input_node.content = "https://example.com/modified"

        # save() should raise ImmutableNodeError
        with pytest.raises(ImmutableNodeError) as exc_info:
            input_node.save()
        assert "structural fields have been modified" in str(exc_info.value)

    def test_uncommitted_node_save_succeeds(self):
        """Verify save() on uncommitted node allows any modification."""
        import random
        comp = Statement(text=f"Original {random.random()}", meaning="test")
        comp.save()  # HEAD state, no hash

        # Modify structural field
        comp.text = "Modified"

        # save() should succeed (uncommitted nodes are mutable)
        comp.save()

        assert comp.hash is None  # Still uncommitted
