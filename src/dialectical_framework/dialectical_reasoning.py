import importlib
import pkgutil
from typing import Union

from dependency_injector import containers, providers
from gqlalchemy import Memgraph, Neo4j

from dialectical_framework.brain import Brain
from dialectical_framework.graph.scoring.tarorank import TaroRank
from dialectical_framework.protocols.antithesis_extractor import AntithesisExtractor
from dialectical_framework.protocols.causality_sequencer import CausalitySequencer
from dialectical_framework.protocols.polarity_finder import PolarityFinder
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
from dialectical_framework.synthesist.ideas.antithesis_extractor_basic import AntithesisExtractorBasic
from dialectical_framework.synthesist.ideas.polarity_finder_basic import PolarityFinderBasic
from dialectical_framework.synthesist.ideas.thesis_extractor_basic import ThesisExtractorBasic
from dialectical_framework.synthesist.polarity.polar_reasoner import PolarReasoner
from dialectical_framework.synthesist.polarity.reason_fast_and_simple import ReasonFastAndSimple
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

    @staticmethod
    def _create_graph_db(settings: Settings) -> Union[Memgraph, Neo4j]:
        """
        Factory method to create the appropriate graph database connection based on vendor.

        Supports common GQLAlchemy connection parameters:
        - host, port: Connection details
        - username, password: Authentication (required for Neo4j, optional for Memgraph)
        - encrypted: Use SSL/TLS connection
        - client_name: Client identification for monitoring
        """
        vendor = settings.graph_db_vendor.lower()

        # Common parameters for both vendors
        common_params = {
            "host": settings.graph_db_host,
            "port": settings.graph_db_port,
            "username": settings.graph_db_username,
            "password": settings.graph_db_password,
            "encrypted": settings.graph_db_encrypted,
            "client_name": settings.graph_db_client_name,
        }

        if vendor == "neo4j":
            # Neo4j requires username/password, provide defaults if not set
            if not common_params["username"]:
                common_params["username"] = "neo4j"
            if not common_params["password"]:
                common_params["password"] = "neo4j"

            return Neo4j(**common_params)

        elif vendor == "memgraph":
            return Memgraph(**common_params)

        else:
            raise ValueError(
                f"Unknown graph_db_vendor: {vendor}. "
                f"Supported vendors: 'memgraph', 'neo4j'"
            )

    # Graph database (Memgraph or Neo4j) for graph-native dialectical structures
    graph_db: providers.Singleton[Union[Memgraph, Neo4j]] = providers.Singleton(
        _create_graph_db,
        settings=settings
    )

    brain: providers.Factory[Brain] = providers.Factory(
        lambda settings: Brain(ai_model=settings.ai_model, ai_provider=settings.ai_provider),
        settings=settings
    )

    polar_reasoner: providers.Factory[PolarReasoner] = providers.Factory(
        ReasonFastAndSimple,
    )


    @staticmethod
    def _create_causality_sequencer(settings: Settings) -> CausalitySequencer:
        """Factory method to create the appropriate causality sequencer based on config"""
        cycle_intent = settings.cycle_intent.lower()

        if cycle_intent in ("preset:desirable", "desirable"):
            return CausalitySequencerDesirable()
        elif cycle_intent in ("preset:feasible", "feasible"):
            return CausalitySequencerFeasible()
        elif cycle_intent in ("preset:realistic", "realistic"):
            return CausalitySequencerRealistic()
        else:
            return CausalitySequencerBalanced()

    causality_sequencer: providers.Factory[CausalitySequencer] = providers.Factory(
        _create_causality_sequencer,
        settings=settings,
    )

    # Focused extractors for idea extraction
    thesis_extractor: providers.Factory[ThesisExtractor] = providers.Factory(
        ThesisExtractorBasic,
    )

    antithesis_extractor: providers.Factory[AntithesisExtractor] = providers.Factory(
        AntithesisExtractorBasic,
    )

    polarity_finder: providers.Factory[PolarityFinder] = providers.Factory(
        PolarityFinderBasic,
    )

    wheel_builder: providers.Factory[WheelBuilder] = providers.Factory(WheelBuilder)

    @staticmethod
    def _create_tarorank(settings: Settings) -> TaroRank:
        """Factory method to create TaroRank scorer with settings-based configuration."""
        return TaroRank(
            alpha=settings.tarorank_alpha,
            default_transition_probability=settings.tarorank_default_transition_probability
        )

    tarorank: providers.Factory[TaroRank] = providers.Factory(
        _create_tarorank,
        settings=settings,
    )

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
