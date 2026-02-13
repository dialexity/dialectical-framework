from enum import Enum


class DI(str, Enum):
    """Dependency injection provider names, for easier refactoring"""

    settings = "settings"
    graph_db = "graph_db"
    brain = "brain"
    polar_reasoner = "polar_reasoner"
    causality_sequencer = "causality_sequencer"

    # Focused extractors for idea extraction
    thesis_extractor = "thesis_extractor"
    antithesis_extractor = "antithesis_extractor"
    polarity_finder = "polarity_finder"

    # Context-aware brainstorming agent
    brainstorming_agent = "brainstorming_agent"

    tarorank = "tarorank"

    # Content resolution (app provides implementation)
    input_resolver = "input_resolver"

    # Scope context for portable identifiers
    scope_context = "scope_context"
