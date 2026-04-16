from enum import Enum


class DI(str, Enum):
    """Dependency injection provider names, for easier refactoring"""

    settings = "settings"
    graph_db = "graph_db"
    brain = "brain"

    tarorank = "tarorank"

    # Content resolution (app provides implementation)
    input_resolver = "input_resolver"

    # Case ID (case_id) - reads from contextvar, set by app layer
    case_id = "case_id"
