# Todo:

[] Transition decorator for constructive transformations (discrete spiral)

[] Multiple cycles by CausalityType on a wheel

[] Add index (numbering) to wheel segments, now we derive it from alias

[] Fake the history of messages, when it's a multi-step stuff

[] Distill chain-of-thought into separate user-assitant messages and keep the history. Instead of providing single prompt with a bunch of reasoning steps to do for LLM 

[] Thesis generation for different use-cases (parametrizable)

[] Control statements calculation for wisdom units

[] Actualization (report generation)

[] Prompt engineering: add examples as user-assistant interchangeable messages, rather than in the big user prompt

[] Make sure everything works when passing thesis (or multiple theses) without the context, i.e. thesis is the context and it's possible to apply dialectics purely based on semantics

[] Make façade that would make it easier to wrap the whole framework into an API

[] Use Lillypad instead of Langfuse

[] Image/Docs upload

[] Domain model classes shouldn't be used to communicate with AI, they're sometimes richer. We should have dedicated "DTOs", from these we'll assemble the domain model.

[] Redefine should not do YES/NO as it constantly doesn't pass. We need an evaluation 0..1 or maybe reevaluate the full wheel during redefine, not restricted on a component level. Problem is most likely is that we don't send the history of chat messages, so AI doesn't see how it was made initially.

[] We should let the analyst create different cycles and evaluate probabilities for them

[] Fix the async bedrock todo, it's a fallback to litellm which ads complexity

[] Parametrized API as in [PROJECT1.md](./PROJECT1.md)

# Done: 
[x] Refactor wheel builders (factories) to be more stateful
