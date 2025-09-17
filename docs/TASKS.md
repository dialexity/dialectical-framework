# Todo:

[] the ability to use these transitions and/or argumentations as starting points for new wheels....

[] Get rid of "reasoning mode", this seems to be connected to brain, which is a pluggable service. Old: DialecticalReasoningMode should be parametrized in config

[] Fidelity score evaluator for a dialectical component
```aiignore
    @prompt_template(
        """
        USER:
        Original source content:
        {source_content}
        
        Extracted dialectical component:
        Alias: {component_alias}
        Statement: {component_statement}
        Explanation: {component_explanation}
        
        <instructions>
        Evaluate how well this dialectical component captures the essence of the source content.
        
        Consider:
        - **Accuracy**: Does it reflect what's actually in the source?
        - **Completeness**: Does it capture the key aspects relevant to its role?
        - **Precision**: Is it specific enough to be meaningful?
        - **Context Preservation**: Does it maintain the original meaning?
        
        Rate from 0.0 (completely misrepresents source) to 1.0 (perfectly captures essence).
        </instructions>
        
        <formatting>
        Output only a float between 0.0 and 1.0
        </formatting>
        """
    )

```

[] Bring the initial context out of the prompts, should be somehow pluggable

[] Recalculate 1 wisdom unit, and then recalculate cycles (needed when T or A is changed), it's an efficient implementation of "redefine"

[] Customizable prompt/rules for thesis extraction. Some sort of "system" prompt for overall analysis?

[] Wheel serialization and incremental maintenance. For every analysis (impacting probabilities) we must have a "meta" info how it was derived, so that in a multi-agent architecture we know that different agetns were working.

[] Linear actions (cycle transitions)
```aiignore
We should add a separate prompt for critical analysis/justification of sequences:
<!--
Sequence Justification and Critical Analysis
-->
Consider the sequence [INSERT SEQUENCE] and the dialectical components from previous analysis.

For each transition in the sequence, provide:

**Causation Logic:**
- Why does [Element A] naturally lead to [Element B]?
- What makes this transition inevitable or logical?
- What underlying forces drive this progression?

**Critical Assessment:**
- Strengths: What makes this transition robust/sustainable?
- Vulnerabilities: Where might this transition fail or stall?
- Alternative paths: What other directions could emerge from [Element A]?

**Real-World Validation:**
- Historical examples where this pattern occurred
- Current systems exhibiting this progression
- Conditions that support vs. hinder this transition

**Conclusion Summary:**
- Is this sequence theoretically sound?
- Is it practically resonant with real systems?
- What makes it transformational vs. merely cyclical?

Output format:
**[Element A] → [Element B]**
- Causation: [Why this happens naturally]
- Strength: [What makes it robust]
- Vulnerability: [Where it might break down]
- Example: [Real-world case]
- Summary insight: [Key takeaway, like "Local clarity exposes structural gaps"]
Settings Integration
Add to settings:
**Sequence Analysis Options:**
☐ Probability assessment (realistic/desirable/feasible)
☐ Causation justification (why transitions occur)
☐ Critical analysis (strengths/vulnerabilities)
☐ Transformation guidance (how to facilitate transitions)
This would give users four distinct but complementary ways to analyze sequences:
Probability - Which sequences work best
Causation - Why sequences work (like your PDF examples)
Critical Analysis - Strengths/weaknesses of sequences
Transformation - How to make sequences happen
The causation analysis (like in your PDF) is indeed a separate and valuable analytical tool that we hadn't explicitly captured in our previous prompts.
```

[] Actualization (report generation)

[] Control statements calculation for wisdom units

[] Image/Docs upload

[] Consolidate wisdom units if the provided theses contain among them also antitheses. The overall number of theses must be ensured still

[] Make sure everything works when passing thesis (or multiple theses) without the context, i.e. thesis is the context and it's possible to apply dialectics purely based on semantics

[] Make façade that would make it easier to wrap the whole framework into an API

[] Use Lillypad instead of Langfuse

[] Redefine should not do YES/NO as it constantly doesn't pass. We need an evaluation 0..1 or maybe reevaluate the full wheel during redefine, not restricted on a component level. Problem is most likely is that we don't send the history of chat messages, so AI doesn't see how it was made initially.

[] Use JSON mode (now it's using tools mode), fallback to tools mode if json mode isn't available on the model, lastly fallback to text mode returning json code block

[] Improve Mirascope to allow html comments in the prompts, which are stripped upon execution.