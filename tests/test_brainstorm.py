"""
Tests for the Brainstorm layer: Brainstorm, Ideas, IntentMixin, and BrainstormingAgent.
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
from dialectical_framework.synthesist.brainstorming_agent import BrainstormingAgent
from dialectical_framework.graph.scope_context import scope


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
        """Vocabulary should include components in the same scope."""

        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            input_node = Input(content="https://article.com")
            input_node.commit()
            brainstorm.inputs.connect(input_node)

            comp = DialecticalComponent(statement="Direct from input")
            comp.commit()
            input_node.statements.connect(comp)

            vocab = DialecticalComponentRepository().get_vocabulary()
            assert len(vocab) == 1
            assert comp in vocab

    def test_vocabulary_from_ideas_statements(self):
        """Vocabulary should include components in the same scope."""

        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
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

            vocab = DialecticalComponentRepository().get_vocabulary()
            assert len(vocab) == 1
            assert comp in vocab

    def test_vocabulary_combines_input_and_ideas(self):
        """Vocabulary should include all components in the same scope."""

        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
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

            vocab = DialecticalComponentRepository().get_vocabulary()
            assert len(vocab) == 2
            assert comp1 in vocab
            assert comp2 in vocab

    def test_vocabulary_across_multiple_inputs(self):
        """Vocabulary should combine components from all Inputs in scope."""

        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
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

            vocab = DialecticalComponentRepository().get_vocabulary()
            assert len(vocab) == 2
            assert comp1 in vocab
            assert comp2 in vocab

    def test_vocabulary_deduplicates(self):
        """Vocabulary should not have duplicate components."""

        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            input_node = Input(content="https://article.com")
            input_node.commit()
            brainstorm.inputs.connect(input_node)

            # Component with same sid
            comp = DialecticalComponent(statement="Shared component")
            comp.commit()
            input_node.statements.connect(comp)

            ideas = Ideas(intent="Extract")
            ideas.save()
            input_node.ideas.connect(ideas)
            ideas.statements.connect(comp)
            ideas.commit()

            vocab = DialecticalComponentRepository().get_vocabulary()
            # Should only appear once (same component)
            assert len(vocab) == 1
            assert comp in vocab

    def test_vocabulary_empty_when_no_components(self):
        """Vocabulary should be empty when no components exist in scope."""

        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            input_node = Input(content="https://article.com")
            input_node.commit()
            brainstorm.inputs.connect(input_node)

            vocab = DialecticalComponentRepository().get_vocabulary()
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

        with scope(brainstorm.sid):
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
            vocab = DialecticalComponentRepository().get_vocabulary()
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


# ============================================================================
# BrainstormingAgent Tests
# ============================================================================


class TestBrainstormingAgentContext:
    """Tests for BrainstormingAgent context awareness methods."""

    def test_create_brainstorm(self):
        """Agent can create a new brainstorm."""
        agent = BrainstormingAgent()
        brainstorm = agent.create_brainstorm()

        assert brainstorm is not None
        assert brainstorm.sid is not None
        assert brainstorm._id is not None  # Committed

    @pytest.mark.asyncio
    async def test_add_input(self):
        """Agent can add input to brainstorm."""
        agent = BrainstormingAgent()
        brainstorm = agent.create_brainstorm()

        input_node = await agent.add_input(brainstorm, "https://example.com/article")

        assert input_node is not None
        assert input_node.content == "https://example.com/article"
        assert input_node.sid == brainstorm.sid
        assert brainstorm.inputs.count() == 1

    def test_get_vocabulary_empty(self):
        """Get vocabulary returns empty set for new brainstorm."""
        agent = BrainstormingAgent()
        brainstorm = agent.create_brainstorm()

        with scope(brainstorm.sid):
            # Create empty input
            input_node = Input(content="test")
            input_node.commit()
            brainstorm.inputs.connect(input_node)

            vocab = agent.get_vocabulary()
            assert len(vocab) == 0

    def test_get_vocabulary_with_components(self):
        """Get vocabulary returns components from brainstorm."""
        agent = BrainstormingAgent()
        brainstorm = agent.create_brainstorm()

        with scope(brainstorm.sid):
            input_node = Input(content="test")
            input_node.commit()
            brainstorm.inputs.connect(input_node)

            comp = DialecticalComponent(statement="Test component")
            comp.commit()
            input_node.statements.connect(comp)

            vocab = agent.get_vocabulary()
            assert len(vocab) == 1
            assert comp in vocab

    def test_get_relationships(self):
        """Get relationships returns components with their relationships."""
        agent = BrainstormingAgent()
        brainstorm = agent.create_brainstorm()

        with scope(brainstorm.sid):
            input_node = Input(content="test")
            input_node.commit()
            brainstorm.inputs.connect(input_node)

            # Create thesis and antithesis
            thesis = DialecticalComponent(statement="Thesis")
            thesis.commit()
            input_node.statements.connect(thesis)

            antithesis = DialecticalComponent(statement="Antithesis")
            antithesis.commit()
            input_node.statements.connect(antithesis)

            # Connect opposition
            thesis.oppositions.connect(antithesis)

            rels = agent.get_relationships(brainstorm)
        assert len(rels) == 2

        # Verify relationship info
        thesis_info = rels[thesis.hash]
        assert thesis_info.component.hash == thesis.hash
        assert thesis_info.has_opposition
        assert len(thesis_info.oppositions) == 1
        assert thesis_info.oppositions[0].hash == antithesis.hash


class TestBrainstormingAgentRejection:
    """Tests for BrainstormingAgent suggestion rejection."""

    def test_reject_suggestion(self):
        """Agent can mark component as rejected."""
        agent = BrainstormingAgent()
        brainstorm = agent.create_brainstorm()

        input_node = Input(content="test", sid=brainstorm.sid)
        input_node.commit()
        brainstorm.inputs.connect(input_node)

        comp = DialecticalComponent(statement="Rejected component", sid=brainstorm.sid)
        comp.commit()
        input_node.statements.connect(comp)

        # Reject with reason
        agent.reject_suggestion(comp, reason="Not relevant")

        # Verify rejection
        assert comp.rejected == "Not relevant"

    def test_rejected_excluded_from_vocabulary_filter(self):
        """Rejected components are in vocabulary but filtered out by agent methods."""
        agent = BrainstormingAgent()
        brainstorm = agent.create_brainstorm()

        with scope(brainstorm.sid):
            input_node = Input(content="test")
            input_node.commit()
            brainstorm.inputs.connect(input_node)

            comp1 = DialecticalComponent(statement="Keep this")
            comp1.commit()
            input_node.statements.connect(comp1)

            comp2 = DialecticalComponent(statement="Reject this")
            comp2.commit()
            input_node.statements.connect(comp2)
            agent.reject_suggestion(comp2, reason="Bad")

            # Vocabulary includes both
            vocab = agent.get_vocabulary()
            assert len(vocab) == 2
            assert comp1 in vocab
            assert comp2 in vocab

            # But suggested components excludes rejected
            suggested = agent.get_suggested_components(brainstorm)
            assert len(suggested) == 1
            assert comp1 in suggested
            assert comp2 not in suggested


class TestBrainstormingAgentConnections:
    """Tests for BrainstormingAgent connection methods."""

    def test_connect_opposition(self):
        """Agent can create opposition between components."""
        agent = BrainstormingAgent()
        brainstorm = agent.create_brainstorm()

        input_node = Input(content="test", sid=brainstorm.sid)
        input_node.commit()
        brainstorm.inputs.connect(input_node)

        thesis = DialecticalComponent(statement="Democracy", sid=brainstorm.sid)
        thesis.commit()
        input_node.statements.connect(thesis)

        antithesis = DialecticalComponent(statement="Autocracy", sid=brainstorm.sid)
        antithesis.commit()
        input_node.statements.connect(antithesis)

        # Connect via agent
        agent.connect_opposition(thesis, antithesis)

        # Verify bidirectional relationship
        assert thesis.oppositions.count() == 1
        opp, _ = thesis.oppositions.get()
        assert opp.hash == antithesis.hash

    def test_connect_positive_side(self):
        """Agent can create positive side relationship."""
        agent = BrainstormingAgent()
        brainstorm = agent.create_brainstorm()

        input_node = Input(content="test", sid=brainstorm.sid)
        input_node.commit()
        brainstorm.inputs.connect(input_node)

        parent = DialecticalComponent(statement="Democracy", sid=brainstorm.sid)
        parent.commit()
        input_node.statements.connect(parent)

        positive = DialecticalComponent(statement="Freedom of speech", sid=brainstorm.sid)
        positive.commit()
        input_node.statements.connect(positive)

        agent.connect_positive_side(positive, parent)

        # Verify relationship
        assert parent.positive_sides.count() == 1
        pos, _ = parent.positive_sides.get()
        assert pos.hash == positive.hash

    def test_connect_negative_side(self):
        """Agent can create negative side relationship."""
        agent = BrainstormingAgent()
        brainstorm = agent.create_brainstorm()

        input_node = Input(content="test", sid=brainstorm.sid)
        input_node.commit()
        brainstorm.inputs.connect(input_node)

        parent = DialecticalComponent(statement="Democracy", sid=brainstorm.sid)
        parent.commit()
        input_node.statements.connect(parent)

        negative = DialecticalComponent(statement="Slow decision making", sid=brainstorm.sid)
        negative.commit()
        input_node.statements.connect(negative)

        agent.connect_negative_side(negative, parent)

        # Verify relationship
        assert parent.negative_sides.count() == 1
        neg, _ = parent.negative_sides.get()
        assert neg.hash == negative.hash


class TestBrainstormingAgentReview:
    """Tests for BrainstormingAgent review methods."""

    def test_get_polarities(self):
        """Get polarities returns thesis-antithesis pairs."""
        agent = BrainstormingAgent()
        brainstorm = agent.create_brainstorm()

        with scope(brainstorm.sid):
            input_node = Input(content="test")
            input_node.commit()
            brainstorm.inputs.connect(input_node)

            thesis = DialecticalComponent(statement="T1")
            thesis.commit()
            input_node.statements.connect(thesis)

            antithesis = DialecticalComponent(statement="A1")
            antithesis.commit()
            input_node.statements.connect(antithesis)

            thesis.oppositions.connect(antithesis)

            pairs = agent.get_polarities(brainstorm)
            assert len(pairs) == 1

            # Check pair contains both
            pair = pairs[0]
            pair_hashes = {pair[0].hash, pair[1].hash}
            assert thesis.hash in pair_hashes
            assert antithesis.hash in pair_hashes

    def test_get_incomplete_components(self):
        """Get incomplete components finds those missing relationships."""
        agent = BrainstormingAgent()
        brainstorm = agent.create_brainstorm()

        with scope(brainstorm.sid):
            input_node = Input(content="test")
            input_node.commit()
            brainstorm.inputs.connect(input_node)

            # Component with no relationships
            lonely = DialecticalComponent(statement="Lonely")
            lonely.commit()
            input_node.statements.connect(lonely)

            # Component with opposition
            thesis = DialecticalComponent(statement="Thesis")
            thesis.commit()
            input_node.statements.connect(thesis)

            antithesis = DialecticalComponent(statement="Antithesis")
            antithesis.commit()
            input_node.statements.connect(antithesis)

            thesis.oppositions.connect(antithesis)

            incomplete = agent.get_incomplete_components(brainstorm)

            # Lonely is missing everything
            assert lonely in incomplete["missing_opposition"]
            assert lonely in incomplete["missing_positive_side"]
            assert lonely in incomplete["missing_negative_side"]

            # Thesis has opposition but missing sides
            assert thesis not in incomplete["missing_opposition"]
            assert thesis in incomplete["missing_positive_side"]
            assert thesis in incomplete["missing_negative_side"]

    def test_get_confirmed_vs_suggested_components(self):
        """Get confirmed and suggested components separates by WU usage."""
        agent = BrainstormingAgent()
        brainstorm = agent.create_brainstorm()

        with scope(brainstorm.sid):
            input_node = Input(content="test")
            input_node.commit()
            brainstorm.inputs.connect(input_node)

            # Create components
            confirmed_comp = DialecticalComponent(statement="In WU")
            confirmed_comp.commit()
            input_node.statements.connect(confirmed_comp)

            suggested_comp = DialecticalComponent(statement="Not in WU")
            suggested_comp.commit()
            input_node.statements.connect(suggested_comp)

            # Put one in a WisdomUnit
            wu = WisdomUnit()
            wu.save()
            wu.t.connect(confirmed_comp, properties={'alias': 'T'})

            # Need to fill WU to commit - add minimal components
            for i, stmt in enumerate(["T+", "T-", "A", "A+", "A-"]):
                c = DialecticalComponent(statement=f"WU comp {stmt}")
                c.commit()
                input_node.statements.connect(c)
                getattr(wu, ['t_plus', 't_minus', 'a', 'a_plus', 'a_minus'][i]).connect(c, properties={'alias': stmt})

            wu.commit()

            # Check separation
            confirmed = agent.get_confirmed_components(brainstorm)
            suggested = agent.get_suggested_components(brainstorm)

            confirmed_hashes = {c.hash for c in confirmed}
            suggested_hashes = {c.hash for c in suggested}

            assert confirmed_comp.hash in confirmed_hashes
            assert suggested_comp.hash in suggested_hashes
            assert confirmed_comp.hash not in suggested_hashes


class TestBrainstormingAgentSuggestionManagement:
    """Tests for BrainstormingAgent suggestion batch management."""

    def test_accept_suggestion_positive_side(self):
        """Accept suggestion creates positive side relationship."""
        agent = BrainstormingAgent()
        brainstorm = agent.create_brainstorm()

        input_node = Input(content="test", sid=brainstorm.sid)
        input_node.commit()
        brainstorm.inputs.connect(input_node)

        parent = DialecticalComponent(statement="Parent", sid=brainstorm.sid)
        parent.commit()
        input_node.statements.connect(parent)

        suggestion = DialecticalComponent(statement="Positive suggestion", sid=brainstorm.sid)
        suggestion.commit()
        input_node.statements.connect(suggestion)

        agent.accept_suggestion(suggestion, parent, relationship_type="positive_side")

        # Verify relationship created
        assert parent.positive_sides.count() == 1

    def test_accept_suggestion_opposition(self):
        """Accept suggestion creates opposition relationship."""
        agent = BrainstormingAgent()
        brainstorm = agent.create_brainstorm()

        input_node = Input(content="test", sid=brainstorm.sid)
        input_node.commit()
        brainstorm.inputs.connect(input_node)

        thesis = DialecticalComponent(statement="Thesis", sid=brainstorm.sid)
        thesis.commit()
        input_node.statements.connect(thesis)

        antithesis = DialecticalComponent(statement="Antithesis suggestion", sid=brainstorm.sid)
        antithesis.commit()
        input_node.statements.connect(antithesis)

        agent.accept_suggestion(antithesis, thesis, relationship_type="opposition")

        # Verify bidirectional relationship
        assert thesis.oppositions.count() == 1


class TestBrainstormingAgentGetSides:
    """Tests for BrainstormingAgent get positive/negative sides methods."""

    def test_get_positive_sides_of(self):
        """Get positive sides returns existing relationships."""
        agent = BrainstormingAgent()

        parent = DialecticalComponent(statement="Parent")
        parent.commit()

        pos1 = DialecticalComponent(statement="Positive 1")
        pos1.commit()
        pos2 = DialecticalComponent(statement="Positive 2")
        pos2.commit()

        pos1.positive_side_of.connect(parent)
        pos2.positive_side_of.connect(parent)

        sides = agent.get_positive_sides_of(parent)
        assert len(sides) == 2
        side_hashes = {s.hash for s in sides}
        assert pos1.hash in side_hashes
        assert pos2.hash in side_hashes

    def test_get_negative_sides_of(self):
        """Get negative sides returns existing relationships."""
        agent = BrainstormingAgent()

        parent = DialecticalComponent(statement="Parent")
        parent.commit()

        neg1 = DialecticalComponent(statement="Negative 1")
        neg1.commit()
        neg1.negative_side_of.connect(parent)

        sides = agent.get_negative_sides_of(parent)
        assert len(sides) == 1
        assert sides[0].hash == neg1.hash


# ============================================================================
# BrainstormingAgent AI-Powered Tests (require LLM)
# ============================================================================


class TestBrainstormingAgentAIPowered:
    """
    Tests for BrainstormingAgent methods that require AI/LLM.

    These tests make real LLM calls and verify the agent's search-first,
    generate-if-needed pattern works correctly.
    """

    @pytest.mark.asyncio
    async def test_find_theses_generates_when_empty(self):
        """Find theses generates new when vocabulary is empty."""
        import uuid
        agent = BrainstormingAgent()
        brainstorm = agent.create_brainstorm()

        with scope(brainstorm.sid):
            # Add input with unique content to avoid collisions with stale test data
            # (Content-addressable dedup can reuse nodes from previous test runs)
            unique_id = str(uuid.uuid4())[:8]
            input_node = Input(
                content=f"Remote work improves productivity and flexibility. [{unique_id}]",
            )
            input_node.commit()
            brainstorm.inputs.connect(input_node)

            # Find theses - should generate since vocabulary is empty
            theses = await agent.find_theses(brainstorm, count=1, generate_if_empty=True)

            assert len(theses) == 1
            assert theses[0].statement  # Should have content

            # Component should be in vocabulary now
            vocab = agent.get_vocabulary()
            assert theses[0] in vocab

    @pytest.mark.asyncio
    async def test_find_theses_returns_existing_when_available(self):
        """Find theses returns existing components when vocabulary has matches."""
        agent = BrainstormingAgent()
        brainstorm = agent.create_brainstorm()

        with scope(brainstorm.sid):
            input_node = Input(content="Remote work discussion.")
            input_node.commit()
            brainstorm.inputs.connect(input_node)

            # Pre-populate vocabulary
            existing = DialecticalComponent(statement="Remote work increases productivity")
            existing.commit()
            input_node.statements.connect(existing)

            # Find theses - should find existing
            theses = await agent.find_theses(brainstorm, intent="productivity", count=1)

            # Should return existing component
            assert len(theses) >= 1
            assert existing.hash in {t.hash for t in theses}

    @pytest.mark.asyncio
    async def test_find_antithesis_generates_new(self):
        """Find antithesis generates new when no candidates exist."""
        agent = BrainstormingAgent()
        brainstorm = agent.create_brainstorm()

        input_node = Input(content="Office work discussion.", sid=brainstorm.sid)
        input_node.commit()
        brainstorm.inputs.connect(input_node)

        thesis = DialecticalComponent(statement="Remote work", sid=brainstorm.sid)
        thesis.commit()
        input_node.statements.connect(thesis)

        # Find antithesis - should generate since no candidates
        antithesis = await agent.find_antithesis_for(brainstorm, thesis, generate_if_missing=True)

        assert antithesis is not None
        assert antithesis.statement  # Should have content
        assert thesis.oppositions.count() == 1  # Should be connected

    @pytest.mark.asyncio
    async def test_find_antithesis_finds_existing(self):
        """Find antithesis returns existing if already connected."""
        agent = BrainstormingAgent()
        brainstorm = agent.create_brainstorm()

        input_node = Input(content="test", sid=brainstorm.sid)
        input_node.commit()
        brainstorm.inputs.connect(input_node)

        thesis = DialecticalComponent(statement="Remote work", sid=brainstorm.sid)
        thesis.commit()
        input_node.statements.connect(thesis)

        existing_antithesis = DialecticalComponent(statement="Office work", sid=brainstorm.sid)
        existing_antithesis.commit()
        input_node.statements.connect(existing_antithesis)

        # Pre-connect opposition
        thesis.oppositions.connect(existing_antithesis)

        # Find antithesis - should return existing
        found = await agent.find_antithesis_for(brainstorm, thesis)

        assert found is not None
        assert found.hash == existing_antithesis.hash

    @pytest.mark.asyncio
    async def test_extract_new_thesis(self):
        """Extract new thesis generates unique component."""
        import uuid
        agent = BrainstormingAgent()
        brainstorm = agent.create_brainstorm()

        # Use unique content to avoid collisions with stale test data
        unique_id = str(uuid.uuid4())[:8]
        input_node = Input(content=f"Remote work enables flexibility and work-life balance. [{unique_id}]", sid=brainstorm.sid)
        input_node.commit()
        brainstorm.inputs.connect(input_node)

        # Extract thesis
        thesis = await agent.extract_new_thesis(brainstorm, intent="flexibility")

        assert thesis is not None
        assert thesis.statement

    @pytest.mark.asyncio
    async def test_extract_new_antithesis(self):
        """Extract new antithesis generates opposition."""
        agent = BrainstormingAgent()
        brainstorm = agent.create_brainstorm()

        input_node = Input(content="Office work discussion.", sid=brainstorm.sid)
        input_node.commit()
        brainstorm.inputs.connect(input_node)

        thesis = DialecticalComponent(statement="Remote work", sid=brainstorm.sid)
        thesis.commit()
        input_node.statements.connect(thesis)

        antithesis = await agent.extract_new_antithesis(brainstorm, thesis)

        assert antithesis is not None
        assert antithesis.statement
        assert thesis.oppositions.count() == 1

    @pytest.mark.asyncio
    async def test_suggest_positive_sides(self):
        """Suggest positive sides generates suggestions."""
        agent = BrainstormingAgent()
        brainstorm = agent.create_brainstorm()

        input_node = Input(content="Democracy enables participation and representation.", sid=brainstorm.sid)
        input_node.commit()
        brainstorm.inputs.connect(input_node)

        parent = DialecticalComponent(statement="Democracy", sid=brainstorm.sid)
        parent.commit()
        input_node.statements.connect(parent)

        ideas, suggestions = await agent.suggest_positive_sides(brainstorm, parent, count=2)

        assert ideas is not None
        assert ideas.intent.startswith("positive_side_of:")
        assert len(suggestions) >= 1
        for s in suggestions:
            assert s.statement

    @pytest.mark.asyncio
    async def test_suggest_negative_sides(self):
        """Suggest negative sides generates suggestions."""
        agent = BrainstormingAgent()
        brainstorm = agent.create_brainstorm()

        input_node = Input(content="Democracy can be slow and inefficient.", sid=brainstorm.sid)
        input_node.commit()
        brainstorm.inputs.connect(input_node)

        parent = DialecticalComponent(statement="Democracy", sid=brainstorm.sid)
        parent.commit()
        input_node.statements.connect(parent)

        ideas, suggestions = await agent.suggest_negative_sides(brainstorm, parent, count=2)

        assert ideas is not None
        assert ideas.intent.startswith("negative_side_of:")
        assert len(suggestions) >= 1


class TestBrainstormingAgentIntegration:
    """Integration tests for full BrainstormingAgent workflow."""

    @pytest.mark.asyncio
    async def test_full_workflow(self):
        """Test complete brainstorming workflow."""
        agent = BrainstormingAgent()

        # 1. Create brainstorm
        brainstorm = agent.create_brainstorm()
        assert brainstorm is not None

        with scope(brainstorm.sid):
            # 2. Add input
            input_node = await agent.add_input(
                brainstorm,
                "Remote work increases productivity by eliminating commute. "
                "However, office work enables better collaboration."
            )
            assert input_node is not None

            # 3. Find theses
            theses = await agent.find_theses(brainstorm, count=2, generate_if_empty=True)
            assert len(theses) >= 1

            # 4. Find antithesis for first thesis
            thesis = theses[0]
            antithesis = await agent.find_antithesis_for(brainstorm, thesis, generate_if_missing=True)
            assert antithesis is not None

            # 5. Get polarities
            pairs = agent.get_polarities(brainstorm)
            assert len(pairs) >= 1

            # 6. Check vocabulary
            vocab = agent.get_vocabulary()
            assert len(vocab) >= 2  # At least thesis and antithesis

            # 7. Get relationships
            rels = agent.get_relationships(brainstorm)
            assert len(rels) >= 2

            # Verify relationship info for thesis
            thesis_info = rels.get(thesis.hash)
            if thesis_info:
                assert thesis_info.has_opposition
