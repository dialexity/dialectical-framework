# dialectical_framework/container.py
import importlib
import os
import pkgutil
from typing import List

from dependency_injector import providers, containers
from dotenv import load_dotenv

from dialectical_framework.brain import Brain
from dialectical_framework.config import Config
from dialectical_framework.enums.causality_type import CausalityType
from dialectical_framework.synthesist.dialectical_reasoner import DialecticalReasoner
from dialectical_framework.synthesist.factories.wheel_builder import WheelBuilder
from dialectical_framework.synthesist.reason_fast_and_simple import ReasonFastAndSimple
from dialectical_framework.synthesist.thought_mapper import ThoughtMapper
from dialectical_framework.wheel import Wheel

# Load environment variables from .env file
load_dotenv()


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

class DialecticalReasoning(containers.DeclarativeContainer):
    """
    Main DI container for the Dialectical Reasoning Framework.

    Provides injectable services for building wheels and calculating transitions.
    """

    wiring_config = containers.WiringConfiguration(
        modules=_discover_modules(),
    )

    config = providers.Singleton(
        lambda: DialecticalReasoning._setup_config()
    )

    brain = providers.Singleton(
        lambda: DialecticalReasoning._setup_brain()
    )

    reasoner = providers.Singleton(
        ReasonFastAndSimple,
        config=config,
        brain=brain,
    )

    causality_analyst = providers.Singleton(
        ThoughtMapper,
        config=config,
        brain=brain
    )

    #
    # --- Factories ---
    #

    @staticmethod
    def create_wheel_builder(
            *,
            text: str = "",
            wheels: List[Wheel] = None,
    ) -> WheelBuilder:
        """Create a WheelBuilder instance from serialized data."""
        return WheelBuilder(
            text=text,
            wheels=wheels,
        )

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



