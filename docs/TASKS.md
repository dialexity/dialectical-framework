# Todo:

[] Linear actions

[] SymmetricTransition is crap. Refactor. Spiral becomes equivalent to converges_constructively predicate. ActionReflection should then inherit from WisdomUnit and TransitionSegmentToSegment. Reciprocal Solution is sort of a spiralic thing as well, which belongs to the WisdomUnit, rather than to the global wheel Spiral. 

[] Actualization (report generation)

[] Syntheses

[] Control statements calculation for wisdom units

[] Image/Docs upload

[] Consolidate wisdom units if the provided theses contain among them also antitheses. The overall number of theses must be ensured still

[] Make sure everything works when passing thesis (or multiple theses) without the context, i.e. thesis is the context and it's possible to apply dialectics purely based on semantics

[] DialecticalReasoningMode should be parametrized in config


[] Add index (numbering) to wheel segments, now we derive it from alias

[] Prompt engineering: add examples as user-assistant interchangeable messages, rather than in the big user prompt

[] Make façade that would make it easier to wrap the whole framework into an API

[] Use Lillypad instead of Langfuse

[] Domain model classes shouldn't be used to communicate with AI, they're sometimes richer. We should have dedicated "DTOs", from these we'll assemble the domain model.

[] Redefine should not do YES/NO as it constantly doesn't pass. We need an evaluation 0..1 or maybe reevaluate the full wheel during redefine, not restricted on a component level. Problem is most likely is that we don't send the history of chat messages, so AI doesn't see how it was made initially.