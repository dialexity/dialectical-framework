from enum import Enum


class DI(str, Enum):
    """Dependency injection provider names, for easier refactoring"""

    settings = "settings"
    graph_db = "graph_db"
    brain = "brain"
    causality_sequencer = "causality_sequencer"

    tarorank = "tarorank"

    # Content resolution (app provides implementation)
    input_resolver = "input_resolver"

    # Scope id (sid) - reads from contextvar, set by app layer
    sid = "sid"
