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
from dialectical_framework.protocols.input_resolver import InputResolver
from dialectical_framework.graph.verbatim_input_resolver import VerbatimInputResolver
from dialectical_framework.graph.dialexity_input_resolver import DialexityInputResolver
from dialectical_framework.graph.composite_input_resolver import CompositeInputResolver
from dialectical_framework.graph.scope_context import ScopeContext


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

            db = Neo4j(**common_params)

        elif vendor == "memgraph":
            db = Memgraph(**common_params)

        else:
            raise ValueError(
                f"Unknown graph_db_vendor: {vendor}. "
                f"Supported vendors: 'memgraph', 'neo4j'"
            )

        # Ensure schema indexes exist
        DialecticalReasoning._ensure_schema(db)
        return db

    @staticmethod
    def _ensure_schema(graph_db: Union[Memgraph, Neo4j]) -> None:
        """
        Ensure required indexes and constraints exist on the graph database.

        Creates indexes on :Node for Merkle identity fields (hash, origin_hash, sid).
        Creates a unique constraint on :Node(hash).
        Works with both Memgraph and Neo4j by detecting DB type and using appropriate syntax.
        """
        required_indexes = {"hash", "origin_hash", "sid"}
        is_neo4j = isinstance(graph_db, Neo4j)

        # Get existing indexes
        existing_indexes: set[str] = set()
        try:
            if is_neo4j:
                # Neo4j: SHOW INDEXES returns labelsOrTypes, properties
                results = graph_db.execute_and_fetch("SHOW INDEXES")
                for row in results:
                    labels = row.get("labelsOrTypes", [])
                    props = row.get("properties", [])
                    if "Node" in labels and props:
                        existing_indexes.update(props)
            else:
                # Memgraph: SHOW INDEX INFO returns label, property
                results = graph_db.execute_and_fetch("SHOW INDEX INFO")
                for row in results:
                    if row.get("label") == "Node":
                        existing_indexes.add(row.get("property"))
        except Exception:
            pass  # Fresh DB - no indexes yet

        # Create missing indexes
        for prop in required_indexes - existing_indexes:
            if is_neo4j:
                # Neo4j 4.x+ syntax with IF NOT EXISTS
                graph_db.execute(
                    f"CREATE INDEX IF NOT EXISTS FOR (n:Node) ON (n.{prop})"
                )
            else:
                # Memgraph syntax
                graph_db.execute(f"CREATE INDEX ON :Node({prop})")

        # Check for existing unique constraint on hash
        has_hash_constraint = False
        try:
            if is_neo4j:
                # Neo4j: SHOW CONSTRAINTS returns labelsOrTypes, properties
                results = graph_db.execute_and_fetch("SHOW CONSTRAINTS")
                for row in results:
                    labels = row.get("labelsOrTypes", [])
                    props = row.get("properties", [])
                    if "Node" in labels and "hash" in props:
                        has_hash_constraint = True
                        break
            else:
                # Memgraph: SHOW CONSTRAINT INFO returns constraint_type, label, properties
                results = graph_db.execute_and_fetch("SHOW CONSTRAINT INFO")
                for row in results:
                    if row.get("label") == "Node" and "hash" in row.get("properties", []):
                        has_hash_constraint = True
                        break
        except Exception:
            pass  # Fresh DB or no constraints

        # Create unique constraint on hash if missing
        if not has_hash_constraint:
            try:
                if is_neo4j:
                    graph_db.execute(
                        "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Node) REQUIRE n.hash IS UNIQUE"
                    )
                else:
                    # Memgraph syntax
                    graph_db.execute(
                        "CREATE CONSTRAINT ON (n:Node) ASSERT n.hash IS UNIQUE"
                    )
            except Exception:
                pass  # Constraint may already exist or DB doesn't support it

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

    # -- Content Resolution --
    # Composite resolver delegates to scheme-specific resolvers:
    # - dx://  -> DialexityInputResolver (internal graph references)
    # - data:  -> VerbatimInputResolver (data URIs)
    # - (else) -> VerbatimInputResolver (plain text)
    #
    # Apps can override with their own InputResolver for production.
    #
    # Example app setup:
    #   class MyAppResolver(InputResolver):
    #       async def resolve(self, input_node, **kwargs):
    #           content = input_node.content
    #           if content.startswith("session://"):
    #               return await self._session_cache.get(content)
    #           # ... handle other schemes
    #
    #   container.input_resolver.override(providers.Singleton(MyAppResolver))
    #
    verbatim_resolver: providers.Singleton[VerbatimInputResolver] = providers.Singleton(
        VerbatimInputResolver
    )

    dialexity_resolver: providers.Singleton[DialexityInputResolver] = providers.Singleton(
        DialexityInputResolver
    )

    input_resolver: providers.Singleton[InputResolver] = providers.Singleton(
        CompositeInputResolver,
        verbatim_resolver=verbatim_resolver,
        dialexity_resolver=dialexity_resolver
    )

    # -- Scope Context for Portable Identifiers --
    # Manages current scope (sid) for node creation using contextvars.
    # All nodes created within a scope context inherit the sid.
    scope_context: providers.Singleton[ScopeContext] = providers.Singleton(
        ScopeContext
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
