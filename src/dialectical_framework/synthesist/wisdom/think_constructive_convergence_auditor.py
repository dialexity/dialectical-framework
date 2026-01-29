from __future__ import annotations

from asyncio import gather
from typing import TYPE_CHECKING

from mirascope import Messages, prompt_template
from mirascope.integrations.langfuse import with_langfuse

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.transition import Transition
    from dialectical_framework.graph.nodes.rationale import Rationale
    from dialectical_framework.graph.wheel_segment import WheelSegment

from dialectical_framework.ai_dto.constructive_convergence_transition_audit_dto import \
    ConstructiveConvergenceTransitionAuditDto
from dialectical_framework.synthesist.wisdom.think_constructive_convergence import ThinkConstructiveConvergence
from dialectical_framework.utils.use_brain import use_brain
from dialectical_framework.graph.nodes.rationale import Rationale as GraphRationale
from dialectical_framework.graph.estimation_manager import EstimationManager
from dialectical_framework.graph.nodes.estimation import FeasibilityEstimation


class ThinkConstructiveConvergenceAuditor(ThinkConstructiveConvergence):
    @prompt_template(
        """
        MESSAGES:
        {think_constructive_convergence}

        ASSISTANT:
        {transition_info}

        USER:
        Evaluate the **practical feasibility** of implementing this transition in real-world conditions.

        **Assessment Criteria:**
        - **Resource requirements** (time, money, skills, infrastructure)
        - **Political/social resistance** or support factors
        - **Structural barriers** or enabling conditions
        - **Timeline realism** for achieving the transition
        - **Precedent cases** where similar transitions succeeded or failed
        - **Contextual constraints** specific to the situation described

        **Feasibility Scale:**
        - **0.0-0.2:** Practically impossible under current conditions
        - **0.3-0.4:** Extremely difficult, would require major systemic changes
        - **0.5-0.6:** Challenging but achievable with significant effort and favorable conditions
        - **0.7-0.8:** Moderately feasible with proper planning and resources
        - **0.9-1.0:** Highly achievable under current or near-term conditions

        **Output Format:**
        Feasibility = [evaluated practical feasibility, number between 0 and 1]
        Key Factors = [2-3 most critical factors affecting feasibility]
        Argumentation = [concise explanation referencing context and evidence]
        Conditions for Success = [what would need to change to improve feasibility]

        **Example:**
        Feasibility = 0.6
        Key Factors = Leadership commitment, resource allocation, change management
        Argumentation = Organizational restructuring is achievable but requires sustained leadership commitment and careful change management to overcome resistance from established hierarchies.
        Conditions for Success = Clear implementation timeline, staff training programs, and measurable equity metrics.
        """
    )
    def prompt_constructive_convergence_audit(self, text: str, transition: Transition, rationale: Rationale) -> "Messages.Type":
        # Extract segments from transition (uses Nexus internally)
        focus = transition.get_source_wheel_segment()
        next_ws = transition.get_target_wheel_segment()

        if not focus or not next_ws:
            raise ValueError(f"Cannot extract wheel segments from transition {transition.uid}")

        return {
            "computed_fields": {
                "think_constructive_convergence": self.prompt_constructive_convergence(text, focus=focus, next_ws=next_ws),
                "transition_info": self._transition_info(transition, r=rationale),
            }
        }

    @with_langfuse()
    @use_brain(response_model=ConstructiveConvergenceTransitionAuditDto)
    async def constructive_convergence_audit(
        self, transition: Transition, rationale: Rationale
    ):
        return self.prompt_constructive_convergence_audit(self._text, transition=transition, rationale=rationale)

    async def think(self, focus: WheelSegment) -> list[Transition]:
        """
        Audit existing transitions for the given wheel segment.

        This method performs feasibility audits on transitions related to the focus segment:
        1. **Spiral transitions** (constructive convergence): T- → next segment's T+
           - Ensures the spiral transition exists by calling parent's think() if not found
        2. **Transformation transitions** (action-reflection): T- → A+ or A- → T+ within same WU
           - Only audits if transformation exists (doesn't create if missing)

        For each transition found, creates audit rationales that critique the original
        rationales based on practical feasibility assessment.

        Args:
            focus: The wheel segment to audit transitions from

        Returns:
            List of transitions that were audited (may have new critique rationales added)

        Note:
            This creates a mix of behaviors:
            - Spiral: Creates if missing (via super().think())
            - Transformation: Only audits if exists (assumes created by ThinkActionReflection)
        """
        # Get representative components for spiral transition (T- → next segment's T+)
        focus_t_minus_result = focus.t_minus.get()

        # For spiral: get next segment in ta_cycle order
        next_ws = self._wheel.get_next_segment(focus)
        next_ws_t_plus_result = next_ws.t_plus.get()

        # === SPIRAL TRANSITIONS (Constructive Convergence) ===
        # Try to find existing spiral transition with same source/target
        spiral_result = self._wheel.spiral.get()
        spiral_link = None

        if focus_t_minus_result and next_ws_t_plus_result and spiral_result:
            source_comp, _ = focus_t_minus_result
            target_comp, _ = next_ws_t_plus_result

            spiral = spiral_result[0]
            spiral_transitions = spiral.transitions

            # Check for duplicate using shared helper
            spiral_link = self.find_duplicate_transition(spiral_transitions, source_comp, target_comp)

        if spiral_link is None:
            # Spiral transition doesn't exist - create it via parent's think()
            # This ensures we always have a spiral transition to audit
            result_list = await super().think(focus=focus)
            if result_list:
                spiral_link = result_list[0]

        # Start with spiral transition (if found/created)
        transitions = [spiral_link] if spiral_link else []

        # === TRANSFORMATION TRANSITIONS (Action-Reflection) ===
        # Only audit if transformation exists (doesn't create if missing)
        # This assumes ThinkActionReflection was already called to create transformations
        wu = self._wheel.wisdom_unit_at(focus)
        transformation_result = wu.transformation.get()
        if transformation_result:
            transformation = transformation_result[0]
            # Get all transformation transitions
            trans_list = transformation.transitions

            # Transformation has exactly 2 fixed transitions within the same WU:
            # - T- → A+ (linear action)
            # - A- → T+ (dialectical reflection)
            # Find the transition that originates from the focus segment
            opposite = focus.opposite

            # Get source (focus minus) and target (opposite plus)
            # WheelSegment properties are polymorphic - t_minus returns T- or A- based on side
            source_minus_result = focus.t_minus.get()
            target_plus_result = opposite.t_plus.get()

            if source_minus_result and target_plus_result:
                source_comp, _ = source_minus_result
                target_comp, _ = target_plus_result
                trans = self.find_duplicate_transition(trans_list, source_comp, target_comp)
                if trans:
                    transitions.append(trans)

        # Build list of (transition, rationale) pairs to audit
        audit_pairs = []
        for transition in transitions:
            rationale_list = [r for r, _ in transition.rationales.all()]
            for r in rationale_list:
                audit_pairs.append((transition, r))

        # Process audits in batches of 3 to avoid hitting API rate limits
        audits: list[ConstructiveConvergenceTransitionAuditDto] = []
        batch_size = 3
        for i in range(0, len(audit_pairs), batch_size):
            batch = audit_pairs[i:i + batch_size]
            # noinspection PyArgumentList
            batch_tasks = [
                self.constructive_convergence_audit(
                    transition=transition,
                    rationale=r
                )
                for transition, r in batch
            ]
            batch_results = await gather(*batch_tasks)
            audits.extend(batch_results)

        # Process all audits and update corresponding transition rationales
        # Zip audit_pairs with audits to ensure correct pairing
        for (transition, rationale), audit in zip(audit_pairs, audits):
            # Create new rationale node as critique
            audit_rationale = GraphRationale(
                text=f"**Key Factors:** {audit.key_factors}\n\n**Argumentation:** {audit.argumentation}\n\n**Conditions for Success:** {audit.success_conditions}",
            )
            audit_rationale.save()

            # Connect as critique FIRST so the graph structure exists
            rationale.critiques.connect(audit_rationale)

            # Store feasibility - this triggers invalidation that now propagates through parents
            # (rationale → transition → spiral → wheel) because the relationship exists
            manager = EstimationManager()
            manager.upsert_estimation(audit_rationale, FeasibilityEstimation, audit.feasibility)

        return transitions