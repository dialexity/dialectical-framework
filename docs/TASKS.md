# Todo:
[] Domain model classes shouldn't be used to communicate with AI, they're sometimes richer. We should have dedicated "DTOs", from these we'll assemble the domain model.

[] Redefine should not do YES/NO as it constantly doesn't pass. We need an evaluation 0..1 or maybe reevaluate the full wheel during redefine, not restricted on a component level. Problem is most likely is that we don't send the history of chat messages, so AI doesn't see how it was made initially.

[] We should let the analyst create different cycles and evaluate probabilities for them

[] Make sure everything works when passing thesis (or multiple theses) without the context, i.e. thesis is the context and it's possible to apply dialectics purely based on semantics

[] Parametrized API as suggested: https://dialexity.slack.com/archives/C08U2N24NDB/p1748413520218259?thread_ts=1748402128.979279&cid=C08U2N24NDB

# Done: 
[x] Refactor wheel builders (factories) to be more stateful
