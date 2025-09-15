import asyncio
from asyncio import gather

from mirascope import Messages, prompt_template
from mirascope.integrations.langfuse import with_langfuse

from dialectical_framework.ai_dto.constructive_convergence_transition_audit_dto import \
    ConstructiveConvergenceTransitionAuditDto
from dialectical_framework.analyst.domain.rationale import Rationale
from dialectical_framework.analyst.domain.transition_segment_to_segment import \
    TransitionSegmentToSegment
from dialectical_framework.analyst.think_constructive_convergence import ThinkConstructiveConvergence
from dialectical_framework.synthesist.domain.wheel_segment import WheelSegment
from dialectical_framework.utils.use_brain import use_brain


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
    def prompt_constructive_convergence_audit(self, text: str, transition: TransitionSegmentToSegment, rationale: Rationale) -> Messages.Type:
        return {
            "computed_fields": {
                "think_constructive_convergence": self.prompt_constructive_convergence(text, focus=transition.source, next_ws=transition.target),
                "transition_info": self._transition_info(transition, rationale),
            }
        }

    @with_langfuse()
    @use_brain(response_model=ConstructiveConvergenceTransitionAuditDto)
    async def constructive_convergence_audit(
        self, transition: TransitionSegmentToSegment, rationale: Rationale
    ):
        return self.prompt_constructive_convergence_audit(self._text, transition=transition, rationale=rationale)

    async def think(self, focus: WheelSegment) -> TransitionSegmentToSegment:
        current_index = self._wheel.index_of(focus)
        next_index = (current_index + 1) % self._wheel.degree
        next_ws = self._wheel.wheel_segment_at(next_index)

        transition = self._wheel.spiral.graph.get_transition([focus.t_minus.alias, focus.t.alias], [next_ws.t_plus.alias])
        if transition is None:
            # Make sure we have the transition
            transition = super().think(focus=focus)

        async_tasks = [
            asyncio.create_task(
                self.constructive_convergence_audit(
                    transition=transition,
                    rationale=r
                )
            )
            for r in transition.rationales
        ]

        audits: list[ConstructiveConvergenceTransitionAuditDto] = await gather(*async_tasks)

        for i, r in enumerate(transition.rationales):
            audit = audits[i]
            r.rationales.append(Rationale(
                contextual_fidelity=audit.feasibility,
                probability=1, # assume the auditor's suggestion is a fact?
                text=f"Key Factors: {audit.key_factors}\n\nArgumentation: {audit.argumentation}\n\nConditions for Success: {audit.success_conditions}"
            ))


        return transition
