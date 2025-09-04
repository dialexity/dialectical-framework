import importlib
import pkgutil

from dependency_injector import containers, providers

from dialectical_framework.brain import Brain
from dialectical_framework.enums.causality_type import CausalityType
from dialectical_framework.protocols.causality_sequencer import \
    CausalitySequencer
from dialectical_framework.protocols.thesis_extractor import ThesisExtractor
from dialectical_framework.settings import Settings
from dialectical_framework.synthesist.causality.causality_sequencer_balanced import \
    CausalitySequencerBalanced
from dialectical_framework.synthesist.causality.causality_sequencer_desirable import \
    CausalitySequencerDesirable
from dialectical_framework.synthesist.causality.causality_sequencer_feasible import \
    CausalitySequencerFeasible
from dialectical_framework.synthesist.causality.causality_sequencer_realistic import \
    CausalitySequencerRealistic
from dialectical_framework.synthesist.concepts.thesis_extractor_basic import \
    ThesisExtractorBasic
from dialectical_framework.synthesist.polarity.polarity_reasoner import \
    PolarityReasoner
from dialectical_framework.synthesist.polarity.reason_fast_and_simple import \
    ReasonFastAndSimple
from dialectical_framework.synthesist.wheel_builder import WheelBuilder


class DialecticalReasoning(containers.DeclarativeContainer):
    """
    Main DI container for the Dialectical Reasoning Framework.

    Provides injectable services for building wheels and calculating transitions.


    IMPORTANT:
    When renaming the fields, make sure to also change it in di.py, as IDE refactoring will not do it automatically.
    """

    @classmethod
    def setup(cls, settings: Settings) -> 'DialecticalReasoning':
        """Create a new container instance with user-specific settings."""
        container = cls()
        container.settings.override(settings)
        return container

    # It will be the same settings for all services in the container
    settings = providers.Dependency(instance_of=Settings)

    brain: providers.Factory[Brain] = providers.Factory(
        lambda settings: Brain(ai_model=settings.ai_model, ai_provider=settings.ai_provider),
        settings=settings
    )

    polarity_reasoner: providers.Factory[PolarityReasoner] = providers.Factory(
        ReasonFastAndSimple,
    )


    @staticmethod
    def _create_causality_sequencer(settings: Settings) -> CausalitySequencer:
        """Factory method to create the appropriate causality sequencer based on config"""
        causality_type = settings.causality_type

        if causality_type == CausalityType.DESIRABLE:
            return CausalitySequencerDesirable()
        elif causality_type == CausalityType.FEASIBLE:
            return CausalitySequencerFeasible()
        elif causality_type == CausalityType.REALISTIC:
            return CausalitySequencerRealistic()
        else:
            return CausalitySequencerBalanced()

    causality_sequencer: providers.Factory[CausalitySequencer] = providers.Factory(
        _create_causality_sequencer,
        settings=settings,
    )

    thesis_extractor: providers.Factory[ThesisExtractor] = providers.Factory(
        ThesisExtractorBasic,
    )

    wheel_builder: providers.Factory[WheelBuilder] = providers.Factory(WheelBuilder)

    # -- Wiring --

    @staticmethod
    def _discover_modules() -> list[str]:
        try:
            package = importlib.import_module("dialectical_framework")
            modules = []

            for _, module_name, _ in pkgutil.walk_packages(
                package.__path__, package.__name__ + "."
            ):
                modules.append(module_name)

            return modules
        except (ImportError, AttributeError):
            # Fallback to empty list if package can't be imported
            return []

    wiring_config = containers.WiringConfiguration(
        modules=_discover_modules(),
    )
