# Todo:

[] Permutations with T-cycles (not only the highest probability)

[] Evaluate every sequence separately, as with longer chains AI starts returning shorter results

[] Normalize "probabilities" for transitions

[] Bring the initial context out of the prompts, should be somehow pluggable

[] Recalculate 1 wisdom unit, and then recalculate cycles (needed when T or A is changed), it's an efficient implementation of "redefine"

[] Customizable prompt/rules for thesis extraction. Some sort of system prompt for overall analysis?

[] For every analysis (imacting probabilities) we must have a "meta" info how it was derived, so that in a multi-agent architecture we know that different agetns were working.

[] Quick Synthesis Conditions
```aiignore
Transitions ("Constructively Converges") could be summarized as "Quick Synthesis Conditions" in just few short lines immediately lifting the wheel's relevance
For instance the typical list of transitions of the 3-concept wheel (provided below) could be compressed to just 6 short statements:
Exploitation → Cultural Transformation: Tie business goals to customer value, engagement, and leadership behaviors.
Micromanagement → Engagement: Shift from control to supportive weekly coaching.
Burnout → Stability: Co-create workflow fixes and act on them fast.
Stagnation (Self-Preservation) → Stability: Trim bureaucracy, keep essential protections.
Stagnation (Passive Mgmt) → Stability: Use forums to modernize processes within rules.
Disengagement → Customer Value: Connect employees directly with customer needs.
```
```aiignore
You are given several transitions between polarities in the format:
 FROM [Pole X- / description] TO [Pole Y+ / description] followed by a longer explanation of how to move from the first to the second.
Your task:
For each transition, produce one ultra-short one-liner (max ~12 words) that:
Captures the essence of the transformation.
Uses active, simple language.
Fits easily inside a polarity map segment.
Focuses on what to do, not the background.
Keep the style consistent with this example set:
Exploitation → Cultural Transformation: Tie business goals to customer value, engagement, and leadership behaviors.
Micromanagement → Engagement: Shift from control to supportive weekly coaching.
Format output as a list:
 [Pole X] → [Pole Y]: [One-liner]
The output could be post-processed with another prompt for even tighter summary (polarity-map ready):
Prompt:
You are given several transitions between polarities in the format:
 FROM [Pole X- / description] TO [Pole Y+ / description] followed by a longer explanation.
Your task:
For each transition, produce a super-compressed action phrase (max 5–8 words) that:
States the key shift or action.
Is polarity-map segment ready.
Avoids background/context — just the transformation.
Format output as:
 [Pole X] → [Pole Y]: [short phrase]
Example:
Exploitation → Cultural Transformation: Link profit to values and people.
Micromanagement → Engagement: Coach, don’t control.
Burnout → Stability: Improve workflows via safe forums.
That way you get both clarity for meaning and brevity for visuals without forcing the AI to guess too much in one step. 
```

[] Linear actions (cycle transitions)
```aiignore
Looking at the Circular Causality Breakdown examples, they're explaining why one element naturally leads to the next (causation/justification), not transforming negative aspects into positive ones. These are different analytical purposes:
Current Analysis Types We Have:
Sequence Probability Analysis - Which sequences are most likely/desirable/feasible
Circular Causality Breakdown - Why each transition happens naturally (causation logic)
Transition Steps - How to transform T1- into T2+ (transformation actions)
Step-by-Step Interpretation - Validation of whether transitions make sense
Missing: Critical Sequence Analysis
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

[] SymmetricTransition is crap. Refactor. Spiral becomes equivalent to converges_constructively predicate. ActionReflection should then inherit from WisdomUnit and TransitionSegmentToSegment. Reciprocal Solution is sort of a spiralic thing as well, which belongs to the WisdomUnit, rather than to the global wheel Spiral. Transition must inherit from DialecticalComponent.

[] Actualization (report generation)

[] Control statements calculation for wisdom units

[] Image/Docs upload

[] Consolidate wisdom units if the provided theses contain among them also antitheses. The overall number of theses must be ensured still

[] Make sure everything works when passing thesis (or multiple theses) without the context, i.e. thesis is the context and it's possible to apply dialectics purely based on semantics

[] DialecticalReasoningMode should be parametrized in config

[] Add index (numbering) to wheel segments, now we derive it from alias

[] Make façade that would make it easier to wrap the whole framework into an API

[] Use Lillypad instead of Langfuse

[] Domain model classes shouldn't be used to communicate with AI, they're sometimes richer. We should have dedicated "DTOs", from these we'll assemble the domain model.

[] Redefine should not do YES/NO as it constantly doesn't pass. We need an evaluation 0..1 or maybe reevaluate the full wheel during redefine, not restricted on a component level. Problem is most likely is that we don't send the history of chat messages, so AI doesn't see how it was made initially.

[] Use JSON mode (now it's using tools mode), fallback to tools mode if json mode isn't available on the model, lastly fallback to text mode returning json code block

[] Improve Mirascope to allow html comments in the prompts, which are stripped upon execution.