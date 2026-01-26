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
        transformation = Transformation(intent="Internal dialectic resolution")
        transformation.save()

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
        ideas.save()

        assert ideas.intent == "Extract productivity claims"
        assert ideas.uid is not None

    def test_ideas_connects_to_input(self):
        """Ideas should connect to Input via DISTILLED_TO."""
        input_node = Input(content_uri="https://article.com")
        input_node.save()

        ideas = Ideas(intent="Extract key arguments")
        ideas.save()

        input_node.ideas.connect(ideas)

        # Verify from Input side
        assert input_node.ideas.count() == 1
        retrieved_ideas, _ = input_node.ideas.get()
        assert retrieved_ideas.uid == ideas.uid

        # Verify from Ideas side
        retrieved_input, _ = ideas.input.get()
        assert retrieved_input.uid == input_node.uid

    def test_ideas_has_statements(self):
        """Ideas can have multiple statements."""
        input_node = Input(content_uri="https://article.com")
        input_node.save()

        ideas = Ideas(intent="Extract claims")
        ideas.save()
        input_node.ideas.connect(ideas)

        comp1 = DialecticalComponent(statement="Remote work improves focus")
        comp1.save()
        comp2 = DialecticalComponent(statement="Office work enables collaboration")
        comp2.save()

        ideas.statements.connect(comp1)
        ideas.statements.connect(comp2)

        assert ideas.statements.count() == 2

    def test_ideas_repr(self):
        """Ideas __repr__ should include count and intent."""
        ideas = Ideas(intent="Test intent")
        ideas.save()

        repr_str = repr(ideas)
        assert "Ideas" in repr_str
        assert "statements=0" in repr_str


class TestBrainstorm:
    """Tests for Brainstorm node."""

    def test_create_brainstorm(self):
        """Brainstorm can be created with intent."""
        brainstorm = Brainstorm(intent="Explore remote work dynamics")
        brainstorm.save()

        assert brainstorm.intent == "Explore remote work dynamics"
        assert brainstorm.uid is not None

    def test_brainstorm_requires_at_least_one_input(self):
        """Brainstorm has cardinality (1, None) for inputs."""
        brainstorm = Brainstorm(intent="Test")
        brainstorm.save()

        # Should be able to connect Input
        input_node = Input(content_uri="https://example.com")
        input_node.save()

        brainstorm.inputs.connect(input_node)
        assert brainstorm.inputs.count() == 1

    def test_brainstorm_can_have_multiple_inputs(self):
        """Brainstorm can have multiple Inputs."""
        brainstorm = Brainstorm(intent="Multi-source analysis")
        brainstorm.save()

        input1 = Input(content_uri="https://source1.com")
        input1.save()
        input2 = Input(content_uri="https://source2.com")
        input2.save()

        brainstorm.inputs.connect(input1)
        brainstorm.inputs.connect(input2)

        assert brainstorm.inputs.count() == 2

    def test_input_reverse_relationship_to_brainstorm(self):
        """Input should be able to find its Brainstorms via _brainstorms."""
        brainstorm = Brainstorm(intent="Test")
        brainstorm.save()

        input_node = Input(content_uri="https://example.com")
        input_node.save()

        brainstorm.inputs.connect(input_node)

        # Check reverse relationship
        assert input_node._brainstorms.count() == 1
        retrieved_brainstorm, _ = input_node._brainstorms.get()
        assert retrieved_brainstorm.uid == brainstorm.uid


class TestBrainstormVocabulary:
    """Tests for Brainstorm.get_vocabulary()."""

    def test_vocabulary_from_input_statements(self):
        """Vocabulary should include components directly from Input."""
        brainstorm = Brainstorm(intent="Test")
        brainstorm.save()

        input_node = Input(content_uri="https://article.com")
        input_node.save()
        brainstorm.inputs.connect(input_node)

        comp = DialecticalComponent(statement="Direct from input")
        comp.save()
        input_node.statements.connect(comp)

        vocab = brainstorm.get_vocabulary()
        assert len(vocab) == 1
        assert comp in vocab

    def test_vocabulary_from_ideas_statements(self):
        """Vocabulary should include components from Ideas."""
        brainstorm = Brainstorm(intent="Test")
        brainstorm.save()

        input_node = Input(content_uri="https://article.com")
        input_node.save()
        brainstorm.inputs.connect(input_node)

        ideas = Ideas(intent="Extract")
        ideas.save()
        input_node.ideas.connect(ideas)

        comp = DialecticalComponent(statement="From ideas")
        comp.save()
        ideas.statements.connect(comp)

        vocab = brainstorm.get_vocabulary()
        assert len(vocab) == 1
        assert comp in vocab

    def test_vocabulary_combines_input_and_ideas(self):
        """Vocabulary should include components from both Input and Ideas."""
        brainstorm = Brainstorm(intent="Test")
        brainstorm.save()

        input_node = Input(content_uri="https://article.com")
        input_node.save()
        brainstorm.inputs.connect(input_node)

        # Direct statement on Input
        comp1 = DialecticalComponent(statement="Direct")
        comp1.save()
        input_node.statements.connect(comp1)

        # Statement via Ideas
        ideas = Ideas(intent="Extract")
        ideas.save()
        input_node.ideas.connect(ideas)

        comp2 = DialecticalComponent(statement="Via ideas")
        comp2.save()
        ideas.statements.connect(comp2)

        vocab = brainstorm.get_vocabulary()
        assert len(vocab) == 2
        assert comp1 in vocab
        assert comp2 in vocab

    def test_vocabulary_across_multiple_inputs(self):
        """Vocabulary should combine components from all Inputs."""
        brainstorm = Brainstorm(intent="Multi-source")
        brainstorm.save()

        input1 = Input(content_uri="https://source1.com")
        input1.save()
        input2 = Input(content_uri="https://source2.com")
        input2.save()

        brainstorm.inputs.connect(input1)
        brainstorm.inputs.connect(input2)

        comp1 = DialecticalComponent(statement="From source 1")
        comp1.save()
        input1.statements.connect(comp1)

        comp2 = DialecticalComponent(statement="From source 2")
        comp2.save()
        input2.statements.connect(comp2)

        vocab = brainstorm.get_vocabulary()
        assert len(vocab) == 2
        assert comp1 in vocab
        assert comp2 in vocab

    def test_vocabulary_deduplicates(self):
        """Vocabulary should not have duplicate components."""
        brainstorm = Brainstorm(intent="Test")
        brainstorm.save()

        input_node = Input(content_uri="https://article.com")
        input_node.save()
        brainstorm.inputs.connect(input_node)

        # Same component connected to both Input and Ideas
        comp = DialecticalComponent(statement="Shared component")
        comp.save()
        input_node.statements.connect(comp)

        ideas = Ideas(intent="Extract")
        ideas.save()
        input_node.ideas.connect(ideas)
        ideas.statements.connect(comp)

        vocab = brainstorm.get_vocabulary()
        # Should only appear once
        assert len(vocab) == 1
        assert comp in vocab

    def test_vocabulary_empty_when_no_components(self):
        """Vocabulary should be empty when no components exist."""
        brainstorm = Brainstorm(intent="Empty")
        brainstorm.save()

        input_node = Input(content_uri="https://article.com")
        input_node.save()
        brainstorm.inputs.connect(input_node)

        vocab = brainstorm.get_vocabulary()
        assert len(vocab) == 0

    def test_brainstorm_repr(self):
        """Brainstorm __repr__ should include count and intent."""
        brainstorm = Brainstorm(intent="Test intent")
        brainstorm.save()

        repr_str = repr(brainstorm)
        assert "Brainstorm" in repr_str
        assert "inputs=0" in repr_str


class TestBrainstormIntegration:
    """Integration tests for the full Brainstorm flow."""

    def test_full_brainstorm_workflow(self):
        """Test the complete brainstorm to vocabulary workflow."""
        # Create brainstorm
        brainstorm = Brainstorm(intent="Explore remote work")
        brainstorm.save()

        # Add input source
        input_node = Input(content_uri="https://article.com/remote-work")
        input_node.save()
        brainstorm.inputs.connect(input_node)

        # Add direct statement
        direct_comp = DialecticalComponent(statement="Remote work is prevalent")
        direct_comp.save()
        input_node.statements.connect(direct_comp)

        # Add ideas extraction
        ideas = Ideas(intent="Extract productivity claims")
        ideas.save()
        input_node.ideas.connect(ideas)

        # Add statements to ideas
        thesis_comp = DialecticalComponent(statement="Remote work improves focus")
        thesis_comp.save()
        antithesis_comp = DialecticalComponent(statement="Office work enables collaboration")
        antithesis_comp.save()

        ideas.statements.connect(thesis_comp)
        ideas.statements.connect(antithesis_comp)

        # Verify vocabulary
        vocab = brainstorm.get_vocabulary()
        assert len(vocab) == 3
        assert direct_comp in vocab
        assert thesis_comp in vocab
        assert antithesis_comp in vocab

        # Verify traversal from component back to brainstorm
        # Component -> Ideas -> Input -> Brainstorm
        input_from_ideas, _ = ideas.input.get()
        assert input_from_ideas.uid == input_node.uid

        brainstorm_from_input, _ = input_node._brainstorms.get()
        assert brainstorm_from_input.uid == brainstorm.uid
