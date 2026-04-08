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
        # Extract segments from transition
        focus = transition.get_source_wheel_segment()
        next_ws = transition.get_target_wheel_segment()

        if not focus or not next_ws:
            raise ValueError(f"Cannot extract wheel segments from transition {transition.hash}")

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

        This method performs feasibility audits on wheel transitions (causality steps)
        related to the focus segment. For each transition found, creates audit rationales
        that critique the original rationales based on practical feasibility assessment.

        Args:
            focus: The wheel segment to audit transitions from

        Returns:
            List of transitions that were audited (may have new critique rationales added)

        Note:
            Creates transition via super().think() if not found.
        """
        # Get representative components for transition (T- → next segment's T+)
        focus_t_minus_result = focus.t_minus.get()

        # Get next segment in ta_cycle order
        next_ws = self._wheel.get_next_segment(focus)
        next_ws_t_plus_result = next_ws.t_plus.get()

        # === WHEEL TRANSITIONS (Constructive Convergence) ===
        # Try to find existing transition with same source/target in wheel's transitions
        wheel_transitions = self._wheel.edges
        causality_link = None

        if focus_t_minus_result and next_ws_t_plus_result and wheel_transitions:
            source_comp, _ = focus_t_minus_result
            target_comp, _ = next_ws_t_plus_result

            # Check for duplicate using shared helper
            causality_link = self.find_duplicate_transition(wheel_transitions, source_comp, target_comp)

        if causality_link is None:
            # Transition doesn't exist - create it via parent's think()
            result_list = await super().think(focus=focus)
            if result_list:
                causality_link = result_list[0]

        # Start with found/created transition
        transitions = [causality_link] if causality_link else []

        # Note: Transformation auditing would go here if needed

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
            audit_rationale.set_critiques_target(rationale)
            audit_rationale.commit()  # Auto-connects as critique

            # Store feasibility - estimation targets the transition, audit_rationale is the provider
            # This triggers invalidation that propagates through parents
            manager = EstimationManager()
            manager.upsert_estimation(transition, FeasibilityEstimation, audit.feasibility, provider=audit_rationale)

        return transitions