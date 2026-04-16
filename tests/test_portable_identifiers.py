"""
Tests for the Merkle identity system: hash, origin_hash, case_id.

These tests verify the identifier model:
- hash (primary identity): sha256 of node's structure + origin_hash
- origin_hash (lineage ID): Parent's hash, preserved across clones
- case_id (scope ID): Case's hash propagates to all descendants
"""

from __future__ import annotations

import pytest

from dialectical_framework.graph.nodes.base_node import ImmutableNodeError
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
from dialectical_framework.graph.nodes.ideas import Ideas
from dialectical_framework.graph.nodes.input import Input
from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit
from dialectical_framework.graph.scope_context import scope, get_current_case_id
from dialectical_framework.graph.repositories.dialectical_component_repository import (
    DialecticalComponentRepository
)


class TestScopeContext:
    """Tests for the scope context functions."""

    def test_default_scope_is_none(self):
        """Default scope should be None."""
        assert get_current_case_id() is None

    def test_context_manager_sets_scope(self):
        """Context manager should set scope within the block."""
        test_case_id = "test-scope-123"

        with scope(test_case_id):
            assert get_current_case_id() == test_case_id

        # After exiting, scope should be restored to None
        assert get_current_case_id() is None

    def test_nested_scopes(self):
        """Nested context managers should work correctly."""
        with scope("outer"):
            assert get_current_case_id() == "outer"

            with scope("inner"):
                assert get_current_case_id() == "inner"

            # After exiting inner, should be back to outer
            assert get_current_case_id() == "outer"

        # After exiting outer, should be None
        assert get_current_case_id() is None


class TestCommitWorkflow:
    """Tests for the commit() workflow (like git commit)."""

    def test_node_starts_in_draft_state(self):
        """New node should start uncommitted (draft state)."""
        comp = DialecticalComponent(statement="Test statement for draft")

        assert not comp.is_committed
        assert comp.hash is None

    def test_save_computes_hash(self):
        """save() should compute hash."""
        import random
        comp = DialecticalComponent(statement=f"Test statement {random.random()}")
        comp.commit()

        assert comp.is_committed
        assert comp.hash is not None
        assert len(comp.hash) == 64  # sha256 hex

    def test_save_is_immutable(self):
        """Calling save() on saved node should raise ImmutableNodeError."""
        import random
        from dialectical_framework.graph.nodes.base_node import ImmutableNodeError
        comp = DialecticalComponent(statement=f"Test statement {random.random()}")
        comp.commit()
        first_hash = comp.hash

        # Second save should raise ImmutableNodeError (node is immutable after save)
        with pytest.raises(ImmutableNodeError):
            comp.commit()

        # Hash should remain unchanged
        assert comp.hash == first_hash

    def test_hash_before_save(self):
        """hash should be None before save."""
        comp = DialecticalComponent(statement="Test")

        # Before save: hash is None
        assert comp.hash is None
        assert not comp.is_committed

    def test_hash_after_save(self):
        """hash should be set after save."""
        comp = DialecticalComponent(statement="Test")
        comp.commit()

        # After save: hash is set
        assert comp.hash is not None
        assert comp.is_committed
        assert len(comp.hash) == 64  # sha256 hex

    def test_save_workflow(self):
        """Standard workflow: create -> save (computes hash and persists)."""
        comp = DialecticalComponent(statement="Test")
        comp.commit()

        assert comp._id is not None
        assert comp.hash is not None

    def test_hash_deterministic(self):
        """Same content should produce same hash (without saving both - would violate unique constraint)."""
        import random
        unique_content = f"Same content {random.random()}"
        comp1 = DialecticalComponent(statement=unique_content)
        comp2 = DialecticalComponent(statement=unique_content)

        # Compute hashes without saving (to test determinism without unique constraint issue)
        hash1 = comp1.compute_hash()
        hash2 = comp2.compute_hash()

        assert hash1 == hash2

        # Also verify by saving one - the saved hash should match
        comp1.commit()
        assert comp1.hash == hash1


class TestCaseIdentifiers:
    """Tests for Case as scope root."""

    def test_case_has_uuid_case_id_on_creation(self):
        """Case generates UUID for case_id on creation."""
        case_node = Case()

        # case_id is set immediately (UUID)
        assert case_node.case_id is not None
        assert len(case_node.case_id) == 36  # UUID format

    def test_case_workflow(self):
        """Full Case workflow: create -> commit (case_id already set)."""
        case_node = Case()
        case_node.commit()

        # case_id is UUID, hash is None (Case never commits)
        assert case_node.case_id is not None
        assert case_node.hash is None


class TestNodeIdentifierInheritance:
    """Tests for case_id inheritance via scope context."""

    def test_input_inherits_case_id_from_context(self):
        """Input created within scope context should inherit case_id."""
        import random
        case_node = Case()
        case_node.commit()

        with scope(case_node.case_id):
            input_node = Input(content=f"https://example.com/{random.random()}")
            input_node.commit()

        assert input_node.case_id == case_node.case_id

    def test_component_inherits_case_id_from_context(self):
        """Component created within scope context should inherit case_id."""
        case_node = Case()
        case_node.commit()

        import random
        with scope(case_node.case_id):
            comp = DialecticalComponent(statement=f"Test statement {random.random()}")
            comp.commit()

        assert comp.case_id == case_node.case_id

    def test_ideas_inherits_case_id_from_context(self):
        """Ideas created within scope context should inherit case_id."""
        import random
        case_node = Case()
        case_node.commit()

        with scope(case_node.case_id):
            ideas = Ideas(intent=f"Test extraction {random.random()}")
            ideas.save()
            ideas.commit()

        assert ideas.case_id == case_node.case_id

    def test_explicit_case_id_overrides_context(self):
        """Explicit case_id parameter should override context."""
        import random
        case_node1 = Case()
        case_node1.commit()

        case_node2 = Case()
        case_node2.commit()

        with scope(case_node1.case_id):
            # Explicit case_id takes precedence
            comp = DialecticalComponent(statement=f"Test {random.random()}", case_id=case_node2.case_id)
            comp.commit()

        assert comp.case_id == case_node2.case_id


class TestOrphanNodes:
    """Tests for nodes created without scope context."""

    def test_node_without_context_has_no_case_id(self):
        """Node created without scope context should have case_id=None."""
        import random
        comp = DialecticalComponent(statement=f"Orphan {random.random()}")
        comp.commit()

        assert comp.case_id is None


class TestCloneOperation:
    """Tests for the clone operation.

    Important: Clone behavior differs between node categories:
    - Atoms (DialecticalComponent, Input, etc.): Content-addressable, NO origin_hash.
      Same content = same hash regardless of cloning.
    - Forking Points (WisdomUnit, Nexus): Have origin_hash for lineage tracking.
      Clones get different hashes due to origin_hash in computation.
    """

    def test_atom_clone_has_same_hash(self):
        """Cloned atom (DialecticalComponent) should have same hash - content-addressable."""
        import random
        case_node1 = Case()
        case_node1.commit()

        case_node2 = Case()
        case_node2.commit()

        with scope(case_node1.case_id):
            original = DialecticalComponent(statement=f"Original statement {random.random()}")
            original.commit()

        cloned = original.clone(destination_case_id=case_node2.case_id)
        cloned.commit()

        # Atoms are content-addressable: same content = same hash
        assert cloned.hash == original.hash

    def test_atom_clone_has_no_origin_hash(self):
        """Cloned atom should NOT have origin_hash - atoms don't track lineage."""
        import random
        case_node1 = Case()
        case_node1.commit()

        with scope(case_node1.case_id):
            original = DialecticalComponent(statement=f"Original {random.random()}")
            original.commit()

        cloned = original.clone(destination_case_id=case_node1.case_id)

        # Atoms don't have origin_hash attribute (not ForkableMixin)
        assert not hasattr(cloned, 'origin_hash') or cloned.origin_hash is None

    def test_clone_sets_new_case_id(self):
        """Cloned node should have the destination case_id."""
        import random
        case_node1 = Case()
        case_node1.commit()

        case_node2 = Case()
        case_node2.commit()

        with scope(case_node1.case_id):
            original = DialecticalComponent(statement=f"Original {random.random()}")
            original.commit()

        cloned = original.clone(destination_case_id=case_node2.case_id)
        cloned.commit()

        assert cloned.case_id == case_node2.case_id

    def test_forking_point_clone_sets_origin_hash(self):
        """Cloned forking point (WisdomUnit) should have origin_hash pointing to original."""
        from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit

        import random
        case_node1 = Case()
        case_node1.commit()

        case_node2 = Case()
        case_node2.commit()

        with scope(case_node1.case_id):
            # Create a complete WisdomUnit (forking point)
            t = DialecticalComponent(statement=f"Thesis {random.random()}")
            t_plus = DialecticalComponent(statement=f"Thesis plus {random.random()}")
            t_minus = DialecticalComponent(statement=f"Thesis minus {random.random()}")
            a = DialecticalComponent(statement=f"Antithesis {random.random()}")
            a_plus = DialecticalComponent(statement=f"Antithesis plus {random.random()}")
            a_minus = DialecticalComponent(statement=f"Antithesis minus {random.random()}")

            for comp in [t, t_plus, t_minus, a, a_plus, a_minus]:
                comp.commit()

            original_wu = WisdomUnit()
            original_wu.save()
            original_wu.t.connect(t, properties={'alias': 'T'})
            original_wu.t_plus.connect(t_plus, properties={'alias': 'T+'})
            original_wu.t_minus.connect(t_minus, properties={'alias': 'T-'})
            original_wu.a.connect(a, properties={'alias': 'A'})
            original_wu.a_plus.connect(a_plus, properties={'alias': 'A+'})
            original_wu.a_minus.connect(a_minus, properties={'alias': 'A-'})
            original_wu.commit()

        cloned_wu = original_wu.clone(destination_case_id=case_node2.case_id)

        # Forking points have origin_hash pointing to source
        assert cloned_wu.origin_hash == original_wu.hash

    def test_forking_point_clone_has_different_hash(self):
        """Cloned forking point should have different hash due to origin_hash."""
        from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit

        import random
        case_node1 = Case()
        case_node1.commit()

        case_node2 = Case()
        case_node2.commit()

        # Create orphan components (case_id=None) so they can be shared across scopes
        # This matches real usage: atoms are global facts, shared across scopes
        t = DialecticalComponent(statement=f"Thesis {random.random()}")
        t_plus = DialecticalComponent(statement=f"Thesis plus {random.random()}")
        t_minus = DialecticalComponent(statement=f"Thesis minus {random.random()}")
        a = DialecticalComponent(statement=f"Antithesis {random.random()}")
        a_plus = DialecticalComponent(statement=f"Antithesis plus {random.random()}")
        a_minus = DialecticalComponent(statement=f"Antithesis minus {random.random()}")

        for comp in [t, t_plus, t_minus, a, a_plus, a_minus]:
            comp.commit()

        with scope(case_node1.case_id):
            original_wu = WisdomUnit()
            original_wu.save()
            original_wu.t.connect(t, properties={'alias': 'T'})
            original_wu.t_plus.connect(t_plus, properties={'alias': 'T+'})
            original_wu.t_minus.connect(t_minus, properties={'alias': 'T-'})
            original_wu.a.connect(a, properties={'alias': 'A'})
            original_wu.a_plus.connect(a_plus, properties={'alias': 'A+'})
            original_wu.a_minus.connect(a_minus, properties={'alias': 'A-'})
            original_wu.commit()

        # Clone and reconnect components (clone doesn't copy relationships)
        # Components are orphans, so they can be connected to WU in any scope
        cloned_wu = original_wu.clone(destination_case_id=case_node2.case_id)
        cloned_wu.save()
        cloned_wu.t.connect(t, properties={'alias': 'T'})
        cloned_wu.t_plus.connect(t_plus, properties={'alias': 'T+'})
        cloned_wu.t_minus.connect(t_minus, properties={'alias': 'T-'})
        cloned_wu.a.connect(a, properties={'alias': 'A'})
        cloned_wu.a_plus.connect(a_plus, properties={'alias': 'A+'})
        cloned_wu.a_minus.connect(a_minus, properties={'alias': 'A-'})
        cloned_wu.commit()

        # Forking points have different hashes due to origin_hash in computation
        assert cloned_wu.hash != original_wu.hash
        assert cloned_wu.origin_hash == original_wu.hash

    def test_clone_returns_uncommitted_node(self):
        """Clone should return uncommitted (draft) node."""
        import random
        case_node1 = Case()
        case_node1.commit()

        with scope(case_node1.case_id):
            original = DialecticalComponent(statement=f"Original {random.random()}")
            original.commit()

        cloned = original.clone(destination_case_id=case_node1.case_id)

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

        with scope(case_node1.case_id):
            original = DialecticalComponent(statement=f"Test statement {random.random()}")
            original.commit()

        cloned = original.clone(destination_case_id=case_node2.case_id)

        assert cloned.statement == original.statement


class TestScopeValidationOnConnect:
    """Tests for scope validation when connecting nodes."""

    def test_same_scope_connection_allowed(self):
        """Nodes from the same scope should connect successfully."""
        import random
        case_node = Case()
        case_node.commit()

        with scope(case_node.case_id):
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

        with scope(case_node2.case_id):
            input_node = Input(content=f"https://example.com/{random.random()}")
            input_node.commit()

        # Try to connect Input (scope2) to Case1 (scope1)
        with pytest.raises(ValueError) as exc_info:
            case_node1.inputs.connect(input_node)

        assert "different scopes" in str(exc_info.value).lower()

    def test_orphan_node_connection_allowed(self):
        """Orphan nodes (case_id=None) should be connectable to any scope."""
        import random
        case_node = Case()
        case_node.commit()

        # Create Input without scope context
        input_node = Input(content=f"https://example.com/{random.random()}")
        input_node.commit()

        assert input_node.case_id is None

        # Should be able to connect to case
        case_node.inputs.connect(input_node)
        assert case_node.inputs.count() == 1


class TestHashLookup:
    """Tests for git-style hash prefix lookup."""

    def test_short_prefix_lookup(self):
        """Should find node by short hash prefix."""
        import random
        from dialectical_framework.graph.repositories.node_repository import NodeRepository

        comp = DialecticalComponent(statement=f"Test for prefix lookup {random.random()}")
        comp.commit()

        repo = NodeRepository()
        found = repo.find_by_hash(comp.hash[:7])

        assert found is not None
        assert found.hash == comp.hash

    def test_prefix_too_short_raises(self):
        """Prefix shorter than 7 chars should raise ValueError."""
        from dialectical_framework.graph.repositories.node_repository import NodeRepository

        repo = NodeRepository()

        with pytest.raises(ValueError) as exc_info:
            repo.find_by_hash("abc")

        assert "at least" in str(exc_info.value).lower()

    def test_find_by_full_hash(self):
        """Should find node by full hash."""
        import random
        from dialectical_framework.graph.repositories.node_repository import NodeRepository

        comp = DialecticalComponent(statement=f"Test for full hash lookup {random.random()}")
        comp.commit()

        repo = NodeRepository()
        found = repo.find_by_hash(comp.hash)

        assert found is not None
        assert found.hash == comp.hash


class TestLineageTracking:
    """Tests for origin_hash lineage tracking.

    Note: origin_hash is only set on forking points (WisdomUnit, Nexus).
    Atoms don't have lineage tracking - they're global facts.
    """

    def test_forking_point_has_origin_hash(self):
        """Cloned forking points (WisdomUnit) should have origin_hash set."""
        import random
        from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit

        case_node1 = Case()
        case_node1.commit()

        # Create orphan components (shared globally)
        t = DialecticalComponent(statement=f"Thesis {random.random()}")
        t_plus = DialecticalComponent(statement=f"Thesis plus {random.random()}")
        t_minus = DialecticalComponent(statement=f"Thesis minus {random.random()}")
        a = DialecticalComponent(statement=f"Antithesis {random.random()}")
        a_plus = DialecticalComponent(statement=f"Antithesis plus {random.random()}")
        a_minus = DialecticalComponent(statement=f"Antithesis minus {random.random()}")

        for comp in [t, t_plus, t_minus, a, a_plus, a_minus]:
            comp.commit()

        with scope(case_node1.case_id):
            original_wu = WisdomUnit(intent="original")
            original_wu.save()
            original_wu.t.connect(t, properties={'alias': 'T'})
            original_wu.t_plus.connect(t_plus, properties={'alias': 'T+'})
            original_wu.t_minus.connect(t_minus, properties={'alias': 'T-'})
            original_wu.a.connect(a, properties={'alias': 'A'})
            original_wu.a_plus.connect(a_plus, properties={'alias': 'A+'})
            original_wu.a_minus.connect(a_minus, properties={'alias': 'A-'})
            original_wu.commit()

        # Original should have no origin_hash
        assert original_wu.origin_hash is None

        # Create fork
        clone = original_wu.clone(destination_case_id=case_node1.case_id)
        clone.intent = "fork"

        # Before commit, origin_hash should be set
        assert clone.origin_hash == original_wu.hash

        # After commit, origin_hash should still be set
        clone.save()
        clone.t.connect(t, properties={'alias': 'T'})
        clone.t_plus.connect(t_plus, properties={'alias': 'T+'})
        clone.t_minus.connect(t_minus, properties={'alias': 'T-'})
        clone.a.connect(a, properties={'alias': 'A'})
        clone.a_plus.connect(a_plus, properties={'alias': 'A+'})
        clone.a_minus.connect(a_minus, properties={'alias': 'A-'})
        clone.commit()

        assert clone.origin_hash == original_wu.hash

        # Verify different hashes due to origin_hash
        assert clone.hash != original_wu.hash

    def test_atoms_have_no_lineage(self):
        """Atoms (DialecticalComponent) should NOT have origin_hash after clone."""
        import random

        case_node = Case()
        case_node.commit()

        with scope(case_node.case_id):
            original = DialecticalComponent(statement=f"Original {random.random()}")
            original.commit()

        clone = original.clone(destination_case_id=case_node.case_id)
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

        assert case_node.case_id is not None
        assert len(case_node.case_id) == 36  # UUID format
        assert case_node.hash is None  # Case never commits

        with scope(case_node.case_id):
            # Create Input
            input_node = Input(content=f"https://example.com/{random.random()}")
            input_node.commit()

            assert input_node.case_id == case_node.case_id

            # Create Ideas (container - save first, commit after statements)
            ideas = Ideas(intent=f"Extract claims {random.random()}")
            ideas.save()

            # Create Component
            comp = DialecticalComponent(statement=f"Test statement {random.random()}")
            comp.commit()

            # Connect statements before commit
            ideas.statements.connect(comp)
            ideas.commit()

        # Connect container relationships
        case_node.inputs.connect(input_node)
        input_node.ideas.connect(ideas)

        # Verify all have same scope
        assert input_node.case_id == case_node.case_id
        assert ideas.case_id == case_node.case_id
        assert comp.case_id == case_node.case_id

        # Verify vocabulary
        repo = DialecticalComponentRepository()
        with scope(case_node.case_id):
            vocab = repo.get_vocabulary()
        assert comp in vocab


class TestHashIntegrityOnSave:
    """Tests for hash integrity verification when calling save() after commit."""

    def test_save_blocks_structural_modification_after_commit(self):
        """Verify save() raises ImmutableNodeError if structural fields modified after commit."""
        import random
        comp = DialecticalComponent(statement=f"Original statement {random.random()}")
        comp.commit()

        # Modify structural field
        comp.statement = "Modified statement"

        # save() should raise ImmutableNodeError
        with pytest.raises(ImmutableNodeError) as exc_info:
            comp.save()
        assert "structural fields have been modified" in str(exc_info.value)

    def test_save_allows_metadata_modification_after_commit(self):
        """Verify save() allows metadata changes after commit."""
        import random
        comp = DialecticalComponent(statement=f"Test statement {random.random()}")
        comp.commit()
        original_hash = comp.hash

        # Modify metadata field
        comp.case_id = "new-scope-id"

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
        comp = DialecticalComponent(statement=f"Original {random.random()}")
        comp.save()  # HEAD state, no hash

        # Modify structural field
        comp.statement = "Modified"

        # save() should succeed (uncommitted nodes are mutable)
        comp.save()

        assert comp.hash is None  # Still uncommitted
