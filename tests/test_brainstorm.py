"""
Tests for the Brainstorm layer: Brainstorm, Ideas, and IntentMixin.
"""

from __future__ import annotations

import pytest

from dialectical_framework.graph.nodes.brainstorm import Brainstorm
from dialectical_framework.graph.nodes.ideas import Ideas
from dialectical_framework.graph.nodes.input import Input
from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit
from dialectical_framework.graph.nodes.nexus import Nexus
from dialectical_framework.graph.nodes.cycle import Cycle
from dialectical_framework.graph.nodes.wheel import Wheel
from dialectical_framework.graph.nodes.transformation import Transformation
from dialectical_framework.graph.nodes.synthesis import Synthesis
from dialectical_framework.graph.nodes.spiral import Spiral
from dialectical_framework.graph.repositories.dialectical_component_repository import (
    DialecticalComponentRepository
)


class TestIntentMixin:
    """Tests for IntentMixin on various nodes."""

    def test_wisdom_unit_has_intent(self):
        """WisdomUnit should have intent field from IntentMixin."""
        wu = WisdomUnit(intent="Analyze work-life balance")
        wu.save()

        assert wu.intent == "Analyze work-life balance"

    def test_nexus_has_intent(self):
        """Nexus should have intent field from IntentMixin."""
        nexus = Nexus(intent="Focus on productivity tensions")
        nexus.save()

        assert nexus.intent == "Focus on productivity tensions"

    def test_cycle_has_intent(self):
        """Cycle should have intent field from IntentMixin."""
        cycle = Cycle(intent="Realistic causal dynamics")
        cycle.save()

        assert cycle.intent == "Realistic causal dynamics"

    def test_wheel_has_intent(self):
        """Wheel should have intent field from IntentMixin."""
        wheel = Wheel(intent="Navigate transformation path")
        wheel.save()

        assert wheel.intent == "Navigate transformation path"

    def test_transformation_has_intent(self):
        """Transformation should have intent field from IntentMixin."""
        # Create WisdomUnit first (required for Transformation)
        wu = WisdomUnit(intent="test_wu")
        wu.save()
        for i, stmt in enumerate(["T", "T+", "T-", "A", "A+", "A-"]):
            c = DialecticalComponent(statement=f"Trans intent test {stmt}")
            c.commit()
            getattr(wu, ['t', 't_plus', 't_minus', 'a', 'a_plus', 'a_minus'][i]).connect(c, properties={'alias': stmt})
        wu.commit()

        transformation = Transformation(intent="Internal dialectic resolution")
        transformation.set_wisdom_unit(wu)
        transformation.commit()

        assert transformation.intent == "Internal dialectic resolution"

    def test_synthesis_has_intent(self):
        """Synthesis should have intent field from IntentMixin."""
        synthesis = Synthesis(intent="Emergent harmony")
        synthesis.save()

        assert synthesis.intent == "Emergent harmony"

    def test_spiral_has_intent(self):
        """Spiral should have intent field from IntentMixin."""
        spiral = Spiral(intent="Meta-synthesis path")
        spiral.save()

        assert spiral.intent == "Meta-synthesis path"

    def test_intent_can_be_none(self):
        """Intent should default to None."""
        wu = WisdomUnit()
        wu.save()

        assert wu.intent is None


class TestIdeas:
    """Tests for Ideas node."""

    def test_create_ideas(self):
        """Ideas can be created with intent."""
        ideas = Ideas(intent="Extract productivity claims")
        ideas.save()  # HEAD state
        ideas.commit()  # Commit with no statements

        assert ideas.intent == "Extract productivity claims"
        assert ideas.hash is not None

    def test_ideas_connects_to_input(self):
        """Ideas should connect to Input via DISTILLED_TO."""
        input_node = Input(content="https://article.com")
        input_node.commit()

        ideas = Ideas(intent="Extract key arguments")
        ideas.save()  # HEAD state
        input_node.ideas.connect(ideas)  # Connect before commit
        ideas.commit()  # Hash includes input hash

        # Verify from Input side
        assert input_node.ideas.count() == 1
        retrieved_ideas, _ = input_node.ideas.get()
        assert retrieved_ideas.hash == ideas.hash

        # Verify from Ideas side
        retrieved_input, _ = ideas.input.get()
        assert retrieved_input.hash == input_node.hash

    def test_ideas_has_statements(self):
        """Ideas can have multiple statements."""
        input_node = Input(content="https://article.com")
        input_node.commit()

        ideas = Ideas(intent="Extract claims")
        ideas.save()  # HEAD state
        input_node.ideas.connect(ideas)

        comp1 = DialecticalComponent(statement="Remote work improves focus")
        comp1.commit()
        comp2 = DialecticalComponent(statement="Office work enables collaboration")
        comp2.commit()

        ideas.statements.connect(comp1)
        ideas.statements.connect(comp2)
        ideas.commit()  # Commit after statements connected

        assert ideas.statements.count() == 2

    def test_ideas_repr(self):
        """Ideas __repr__ should include count and intent."""
        ideas = Ideas(intent="Test intent")
        ideas.save()
        ideas.commit()

        repr_str = repr(ideas)
        assert "Ideas" in repr_str
        assert "statements=0" in repr_str


class TestBrainstorm:
    """Tests for Brainstorm node."""

    def test_create_brainstorm(self):
        """Brainstorm can be created and saved."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        # Brainstorm is a scope root with UUID sid, hash is always None
        assert brainstorm.sid is not None
        assert brainstorm.hash is None

    def test_brainstorm_requires_at_least_one_input(self):
        """Brainstorm has cardinality (1, None) for inputs."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        # Should be able to connect Input
        input_node = Input(content="https://example.com")
        input_node.commit()

        brainstorm.inputs.connect(input_node)
        assert brainstorm.inputs.count() == 1

    def test_brainstorm_can_have_multiple_inputs(self):
        """Brainstorm can have multiple Inputs."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        input1 = Input(content="https://source1.com")
        input1.commit()
        input2 = Input(content="https://source2.com")
        input2.commit()

        brainstorm.inputs.connect(input1)
        brainstorm.inputs.connect(input2)

        assert brainstorm.inputs.count() == 2

    def test_input_reverse_relationship_to_brainstorm(self):
        """Input should be able to find its Brainstorms via _brainstorms."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        input_node = Input(content="https://example.com")
        input_node.commit()

        brainstorm.inputs.connect(input_node)

        # Check reverse relationship
        assert input_node._brainstorms.count() == 1
        retrieved_brainstorm, _ = input_node._brainstorms.get()
        assert retrieved_brainstorm.hash == brainstorm.hash


class TestBrainstormVocabulary:
    """Tests for DialecticalComponentRepository.get_vocabulary(brainstorm)."""

    def test_vocabulary_from_input_statements(self):
        """Vocabulary should include components directly from Input."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        input_node = Input(content="https://article.com")
        input_node.commit()
        brainstorm.inputs.connect(input_node)

        comp = DialecticalComponent(statement="Direct from input")
        comp.commit()
        input_node.statements.connect(comp)

        vocab = DialecticalComponentRepository().get_vocabulary(brainstorm)
        assert len(vocab) == 1
        assert comp in vocab

    def test_vocabulary_from_ideas_statements(self):
        """Vocabulary should include components from Ideas."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        input_node = Input(content="https://article.com")
        input_node.commit()
        brainstorm.inputs.connect(input_node)

        ideas = Ideas(intent="Extract")
        ideas.save()
        input_node.ideas.connect(ideas)

        comp = DialecticalComponent(statement="From ideas")
        comp.commit()
        ideas.statements.connect(comp)
        ideas.commit()

        vocab = DialecticalComponentRepository().get_vocabulary(brainstorm)
        assert len(vocab) == 1
        assert comp in vocab

    def test_vocabulary_combines_input_and_ideas(self):
        """Vocabulary should include components from both Input and Ideas."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        input_node = Input(content="https://article.com")
        input_node.commit()
        brainstorm.inputs.connect(input_node)

        # Direct statement on Input
        comp1 = DialecticalComponent(statement="Direct")
        comp1.commit()
        input_node.statements.connect(comp1)

        # Statement via Ideas
        ideas = Ideas(intent="Extract")
        ideas.save()
        input_node.ideas.connect(ideas)

        comp2 = DialecticalComponent(statement="Via ideas")
        comp2.commit()
        ideas.statements.connect(comp2)
        ideas.commit()

        vocab = DialecticalComponentRepository().get_vocabulary(brainstorm)
        assert len(vocab) == 2
        assert comp1 in vocab
        assert comp2 in vocab

    def test_vocabulary_across_multiple_inputs(self):
        """Vocabulary should combine components from all Inputs."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        input1 = Input(content="https://source1.com")
        input1.commit()
        input2 = Input(content="https://source2.com")
        input2.commit()

        brainstorm.inputs.connect(input1)
        brainstorm.inputs.connect(input2)

        comp1 = DialecticalComponent(statement="From source 1")
        comp1.commit()
        input1.statements.connect(comp1)

        comp2 = DialecticalComponent(statement="From source 2")
        comp2.commit()
        input2.statements.connect(comp2)

        vocab = DialecticalComponentRepository().get_vocabulary(brainstorm)
        assert len(vocab) == 2
        assert comp1 in vocab
        assert comp2 in vocab

    def test_vocabulary_deduplicates(self):
        """Vocabulary should not have duplicate components."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        input_node = Input(content="https://article.com")
        input_node.commit()
        brainstorm.inputs.connect(input_node)

        # Same component connected to both Input and Ideas
        comp = DialecticalComponent(statement="Shared component")
        comp.commit()
        input_node.statements.connect(comp)

        ideas = Ideas(intent="Extract")
        ideas.save()
        input_node.ideas.connect(ideas)
        ideas.statements.connect(comp)
        ideas.commit()

        vocab = DialecticalComponentRepository().get_vocabulary(brainstorm)
        # Should only appear once
        assert len(vocab) == 1
        assert comp in vocab

    def test_vocabulary_empty_when_no_components(self):
        """Vocabulary should be empty when no components exist."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        input_node = Input(content="https://article.com")
        input_node.commit()
        brainstorm.inputs.connect(input_node)

        vocab = DialecticalComponentRepository().get_vocabulary(brainstorm)
        assert len(vocab) == 0

    def test_brainstorm_repr(self):
        """Brainstorm __repr__ should include count."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        repr_str = repr(brainstorm)
        assert "Brainstorm" in repr_str
        assert "inputs=0" in repr_str


class TestBrainstormIntegration:
    """Integration tests for the full Brainstorm flow."""

    def test_full_brainstorm_workflow(self):
        """Test the complete brainstorm to vocabulary workflow."""
        # Create brainstorm
        brainstorm = Brainstorm()
        brainstorm.commit()

        # Add input source
        input_node = Input(content="https://article.com/remote-work")
        input_node.commit()
        brainstorm.inputs.connect(input_node)

        # Add direct statement
        direct_comp = DialecticalComponent(statement="Remote work is prevalent")
        direct_comp.commit()
        input_node.statements.connect(direct_comp)

        # Add ideas extraction
        ideas = Ideas(intent="Extract productivity claims")
        ideas.save()
        input_node.ideas.connect(ideas)

        # Add statements to ideas (before commit)
        thesis_comp = DialecticalComponent(statement="Remote work improves focus")
        thesis_comp.commit()
        antithesis_comp = DialecticalComponent(statement="Office work enables collaboration")
        antithesis_comp.commit()

        ideas.statements.connect(thesis_comp)
        ideas.statements.connect(antithesis_comp)
        ideas.commit()

        # Verify vocabulary
        vocab = DialecticalComponentRepository().get_vocabulary(brainstorm)
        assert len(vocab) == 3
        assert direct_comp in vocab
        assert thesis_comp in vocab
        assert antithesis_comp in vocab

        # Verify traversal from component back to brainstorm
        # Component -> Ideas -> Input -> Brainstorm
        input_from_ideas, _ = ideas.input.get()
        assert input_from_ideas.hash == input_node.hash

        brainstorm_from_input, _ = input_node._brainstorms.get()
        assert brainstorm_from_input.hash == brainstorm.hash


class TestBrainstormDxUriTracing:
    """Tests for dx:// URI Gen-0 tracing in Brainstorm vocabulary."""

    def test_non_dx_input_included_in_vocabulary(self):
        """Non-dx:// Inputs should be included in Gen-0 vocabulary."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        # Regular non-dx:// Input
        input_node = Input(content="https://article.com/test", sid=brainstorm.sid)
        input_node.commit()
        brainstorm.inputs.connect(input_node)

        comp = DialecticalComponent(statement="Test component", sid=brainstorm.sid)
        comp.commit()
        input_node.statements.connect(comp)

        vocab = DialecticalComponentRepository().get_vocabulary(brainstorm)
        assert len(vocab) == 1
        assert comp in vocab

    def test_dx_input_with_valid_gen0_root_included(self):
        """dx:// Input tracing to valid Gen-0 root should be included."""
        from dialectical_framework.graph.nodes.rationale import Rationale

        brainstorm = Brainstorm()
        brainstorm.commit()

        # Create a non-dx:// Input with a component (the Gen-0 root)
        root_input = Input(content="https://original-source.com", sid=brainstorm.sid)
        root_input.commit()
        brainstorm.inputs.connect(root_input)

        root_comp = DialecticalComponent(statement="Original component", sid=brainstorm.sid)
        root_comp.commit()
        root_input.statements.connect(root_comp)

        # Create a Rationale explaining the root component
        rationale = Rationale(text="Explanation of the component", sid=brainstorm.sid)
        rationale.set_explanation(root_comp)
        rationale.commit()

        # Create a dx:// Input referencing the Rationale
        dx_uri = f"dx://{brainstorm.sid}/{rationale.hash}"
        dx_input = Input(content=dx_uri, sid=brainstorm.sid)
        dx_input.commit()
        brainstorm.inputs.connect(dx_input)

        # Create a derived component from the dx:// Input
        derived_comp = DialecticalComponent(statement="Derived component", sid=brainstorm.sid)
        derived_comp.commit()
        dx_input.statements.connect(derived_comp)

        # Both components should be in vocabulary
        vocab = DialecticalComponentRepository().get_vocabulary(brainstorm)
        vocab_hashes = {c.hash for c in vocab}

        assert root_comp.hash in vocab_hashes, "Root component should be in vocabulary"
        assert derived_comp.hash in vocab_hashes, "Derived component should be in vocabulary (dx:// traces to Gen-0)"

    def test_dx_input_with_unresolvable_hash_excluded(self):
        """dx:// Input with unresolvable hash should be excluded."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        # Create a dx:// Input with a non-existent hash
        fake_hash = "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
        dx_uri = f"dx://{brainstorm.sid}/{fake_hash}"
        dx_input = Input(content=dx_uri, sid=brainstorm.sid)
        dx_input.commit()
        brainstorm.inputs.connect(dx_input)

        # Create a component from the unresolvable dx:// Input
        orphan_comp = DialecticalComponent(statement="Orphan component", sid=brainstorm.sid)
        orphan_comp.commit()
        dx_input.statements.connect(orphan_comp)

        # The orphan component should NOT be in vocabulary
        vocab = DialecticalComponentRepository().get_vocabulary(brainstorm)
        vocab_hashes = {c.hash for c in vocab}

        assert orphan_comp.hash not in vocab_hashes, "Component from unresolvable dx:// should be excluded"

    def test_dx_input_with_wrong_sid_excluded(self):
        """dx:// Input with mismatched sid should be excluded."""
        from dialectical_framework.graph.nodes.rationale import Rationale

        brainstorm = Brainstorm()
        brainstorm.commit()

        # Create a root Input and component
        root_input = Input(content="https://source.com", sid=brainstorm.sid)
        root_input.commit()
        brainstorm.inputs.connect(root_input)

        root_comp = DialecticalComponent(statement="Root", sid=brainstorm.sid)
        root_comp.commit()
        root_input.statements.connect(root_comp)

        # Create a Rationale
        rationale = Rationale(text="Explanation", sid=brainstorm.sid)
        rationale.set_explanation(root_comp)
        rationale.commit()

        # Create a dx:// Input with WRONG sid in the URI
        wrong_sid = "wrong-sid-12345678"
        dx_uri = f"dx://{wrong_sid}/{rationale.hash}"  # URI has wrong sid
        dx_input = Input(content=dx_uri, sid=brainstorm.sid)  # Input has correct sid
        dx_input.commit()
        brainstorm.inputs.connect(dx_input)

        wrong_comp = DialecticalComponent(statement="Wrong scope", sid=brainstorm.sid)
        wrong_comp.commit()
        dx_input.statements.connect(wrong_comp)

        vocab = DialecticalComponentRepository().get_vocabulary(brainstorm)
        vocab_hashes = {c.hash for c in vocab}

        assert root_comp.hash in vocab_hashes, "Root component should be included"
        assert wrong_comp.hash not in vocab_hashes, "Component from dx:// with wrong sid should be excluded"

    def test_dx_input_tracing_via_ideas_born_component(self):
        """dx:// tracing should work for Ideas-born components (not just direct Input-born)."""
        from dialectical_framework.graph.nodes.rationale import Rationale

        brainstorm = Brainstorm()
        brainstorm.commit()

        # Create a root Input with Ideas (not direct HAS_STATEMENT)
        root_input = Input(content="https://original-article.com", sid=brainstorm.sid)
        root_input.commit()
        brainstorm.inputs.connect(root_input)

        # Create Ideas and connect component via Ideas (not direct Input)
        ideas = Ideas(intent="extraction", sid=brainstorm.sid)
        ideas.save()
        root_input.ideas.connect(ideas)

        ideas_born_comp = DialecticalComponent(statement="Ideas-born component", sid=brainstorm.sid)
        ideas_born_comp.commit()
        ideas.statements.connect(ideas_born_comp)  # Via Ideas, not Input
        ideas.commit()

        # Create a Rationale explaining the Ideas-born component
        rationale = Rationale(text="Explanation of Ideas-born", sid=brainstorm.sid)
        rationale.set_explanation(ideas_born_comp)
        rationale.commit()

        # Create a dx:// Input referencing the Rationale
        dx_uri = f"dx://{brainstorm.sid}/{rationale.hash}"
        dx_input = Input(content=dx_uri, sid=brainstorm.sid)
        dx_input.commit()
        brainstorm.inputs.connect(dx_input)

        # Create a derived component from the dx:// Input
        derived_comp = DialecticalComponent(statement="Derived from Ideas-born", sid=brainstorm.sid)
        derived_comp.commit()
        dx_input.statements.connect(derived_comp)

        # Both components should be in vocabulary
        vocab = DialecticalComponentRepository().get_vocabulary(brainstorm)
        vocab_hashes = {c.hash for c in vocab}

        assert ideas_born_comp.hash in vocab_hashes, "Ideas-born component should be in vocabulary"
        assert derived_comp.hash in vocab_hashes, "Derived component should be in vocabulary (dx:// traces via Ideas)"


def test_brainstorm_vocabulary_includes_derivative_dx_inputs():
    """
    Test that Brainstorm vocabulary includes components from derivative dx:// Inputs
    that are NOT connected via HAS_INPUT but reference content within the Brainstorm's scope.

    This enables Gen-0 analytical work where:
    1. A Rationale explains a Component from a HAS_INPUT Input
    2. A new Input with dx://brainstorm-sid/rationale-hash extracts new statements
    3. Those statements should be part of the Brainstorm's vocabulary
       even without explicit HAS_INPUT connection
    """
    from dialectical_framework.graph.nodes.rationale import Rationale
    from dialectical_framework.graph.scope_context import ScopeContext

    # Create Brainstorm with unique sid
    brainstorm = Brainstorm()
    brainstorm.save()
    brainstorm_sid = brainstorm.sid

    ctx = ScopeContext()
    with ctx.scope(brainstorm_sid):
        # Create a HAS_INPUT Input with a component
        root_input = Input(content="https://example.com/article")
        root_input.commit()
        brainstorm.inputs.connect(root_input)

        original_comp = DialecticalComponent(statement="Original statement from article")
        original_comp.commit()
        root_input.statements.connect(original_comp)

        # Create a Rationale explaining the original component
        rationale = Rationale(text="This statement means...")
        rationale.set_explanation(original_comp)
        rationale.commit()

        # Create a derivative dx:// Input referencing the Rationale
        # NOTE: This Input is NOT connected to Brainstorm via HAS_INPUT
        dx_uri = f"dx://{brainstorm_sid}/{rationale.hash}"
        derivative_input = Input(content=dx_uri)
        derivative_input.commit()
        # NO brainstorm.inputs.connect(derivative_input) - intentionally not connected!

        # Create a derived component from the derivative Input
        derived_comp = DialecticalComponent(statement="New insight derived from rationale")
        derived_comp.commit()
        derivative_input.statements.connect(derived_comp)

        # Get vocabulary
        vocab = DialecticalComponentRepository().get_vocabulary(brainstorm)
        vocab_hashes = {c.hash for c in vocab}

        # Original component should be in vocabulary (via HAS_INPUT)
        assert original_comp.hash in vocab_hashes, \
            "Original component should be in vocabulary"

        # Derived component should ALSO be in vocabulary (via dx:// tracing)
        assert derived_comp.hash in vocab_hashes, \
            "Derived component from dx:// Input (not HAS_INPUT) should be in vocabulary"

        print("✅ Derivative dx:// Input components included in Gen-0 vocabulary")
