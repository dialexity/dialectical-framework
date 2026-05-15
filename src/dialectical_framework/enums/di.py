from enum import Enum


class DI(str, Enum):
    """Dependency injection provider names, for easier refactoring"""

    settings = "settings"
    graph_db = "graph_db"

    # Content resolution (app provides implementation)
    input_resolver = "input_resolver"

    # Scope ID (sid) - reads from contextvar, set by app layer
    sid = "sid"

    # Event bus for graph mutation fan-out
    event_bus = "event_bus"
