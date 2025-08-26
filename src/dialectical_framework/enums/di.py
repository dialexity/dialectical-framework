from enum import Enum


class DI(str, Enum):
    """Dependency injection provider names, for easier refactoring"""
    config = "config"
    brain = "brain"
    polarity_reasoner = "polarity_reasoner"
    causality_sequencer = "causality_sequencer"
    thesis_extractor = "thesis_extractor"