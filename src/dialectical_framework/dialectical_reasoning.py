import importlib
import os
import pkgutil
from typing import List

from dependency_injector import providers, containers
from dotenv import load_dotenv

from dialectical_framework.brain import Brain
from dialectical_framework.config import Config
from dialectical_framework.enums.causality_type import CausalityType
from dialectical_framework.synthesist.causality.causality_sequencer_balanced import CausalitySequencerBalanced
from dialectical_framework.synthesist.causality.causality_sequencer_desirable import CausalitySequencerDesirable
from dialectical_framework.synthesist.causality.causality_sequencer_feasible import CausalitySequencerFeasible
from dialectical_framework.synthesist.causality.causality_sequencer_realistic import CausalitySequencerRealistic
from dialectical_framework.synthesist.concepts.thesis_extractor_basic import ThesisExtractorBasic
from dialectical_framework.synthesist.polarity.reason_fast_and_simple import ReasonFastAndSimple
from dialectical_framework.synthesist.wheel_builder import WheelBuilder

# Load environment variables from .env file
load_dotenv()

class DialecticalReasoning(containers.DeclarativeContainer):
    """
    Main DI container for the Dialectical Reasoning Framework.

    Provides injectable services for building wheels and calculating transitions.


    IMPORTANT:
    When renaming the fields, make sure to also change it in di.py, as IDE refactoring will not do it automatically.
    """

    brain = providers.Singleton(
        lambda: DialecticalReasoning._setup_brain()
    )

    config = providers.Singleton(
        lambda: DialecticalReasoning._setup_config()
    )

    polarity_reasoner = providers.Singleton(
        ReasonFastAndSimple,
    )

    causality_sequencer = providers.Singleton(
        lambda config: DialecticalReasoning._create_causality_sequencer(config),
        config=config
    )

    thesis_extractor = providers.Singleton(
        ThesisExtractorBasic,
    )

    wheel_builder = providers.Factory(
        WheelBuilder
    )

    #
    # --- Factory/Strategy ---
    #
    @staticmethod
    def _create_causality_sequencer(config: Config):
        """Factory method to create the appropriate causality sequencer based on config"""
        causality_type = config.causality_type

        if causality_type == CausalityType.DESIRABLE:
            return CausalitySequencerDesirable()
        elif causality_type == CausalityType.FEASIBLE:
            return CausalitySequencerFeasible()
        elif causality_type == CausalityType.REALISTIC:
            return CausalitySequencerRealistic()
        else:
            return CausalitySequencerBalanced()

    #
    # --- Setup Helpers ---
    #

    @staticmethod
    def _setup_brain() -> Brain:
        model = os.getenv("DIALEXITY_DEFAULT_MODEL", None)
        provider = os.getenv("DIALEXITY_DEFAULT_MODEL_PROVIDER", None)
        missing = []
        if not model:
            missing.append('DIALEXITY_DEFAULT_MODEL')
        if not provider:
            if "/" not in model:
                missing.append('DIALEXITY_DEFAULT_MODEL_PROVIDER')
            else:
                # We will give litellm a chance to derive the provider from the model
                pass
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

        return Brain(ai_model=model, ai_provider=provider)

    @staticmethod
    def _setup_config() -> Config:
        """
        Static method to set up and return a Config instance.
        It uses environment variables or hardcoded defaults for configuration.
        """
        component_length = int(os.getenv("DIALEXITY_DEFAULT_COMPONENT_LENGTH", 7))
        causality_type = CausalityType(os.getenv("DIALEXITY_DEFAULT_CAUSALITY_TYPE", CausalityType.BALANCED.value))

        return Config(
            component_length=component_length,
            causality_type=causality_type,
        )

    # -- Wiring --

    @staticmethod
    def _discover_modules() -> List[str]:
        try:
            package = importlib.import_module("dialectical_framework")
            modules = []

            for _, module_name, _ in pkgutil.walk_packages(
                    package.__path__,
                    package.__name__ + "."
            ):
                modules.append(module_name)

            return modules
        except (ImportError, AttributeError):
            # Fallback to empty list if package can't be imported
            return []

    wiring_config = containers.WiringConfiguration(
        modules=_discover_modules(),
    )

