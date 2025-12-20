"""
Database connection configuration for Memgraph.

This module provides connection management for the dialectical framework's
graph database using GQLAlchemy OGM with Memgraph.
"""

from __future__ import annotations

import os
from typing import Optional

from gqlalchemy import Memgraph


class DatabaseConfig:
    """Configuration for Memgraph database connection."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 7687,
        username: str = "",
        password: str = "",
        encrypted: bool = False,
        lazy: bool = True,
    ):
        """
        Initialize database configuration.

        Args:
            host: Memgraph host address
            port: Memgraph port (default: 7687)
            username: Database username (optional)
            password: Database password (optional)
            encrypted: Use encrypted connection (default: False)
            lazy: Lazy connection (default: True)
        """
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.encrypted = encrypted
        self.lazy = lazy

    @classmethod
    def from_env(cls) -> DatabaseConfig:
        """
        Create configuration from environment variables.

        Environment variables:
            MEMGRAPH_HOST: Database host (default: 127.0.0.1)
            MEMGRAPH_PORT: Database port (default: 7687)
            MEMGRAPH_USERNAME: Database username (optional)
            MEMGRAPH_PASSWORD: Database password (optional)
            MEMGRAPH_ENCRYPTED: Use encryption (default: false)

        Returns:
            DatabaseConfig instance
        """
        return cls(
            host=os.getenv("MEMGRAPH_HOST", "127.0.0.1"),
            port=int(os.getenv("MEMGRAPH_PORT", "7687")),
            username=os.getenv("MEMGRAPH_USERNAME", ""),
            password=os.getenv("MEMGRAPH_PASSWORD", ""),
            encrypted=os.getenv("MEMGRAPH_ENCRYPTED", "false").lower() == "true",
        )


class DatabaseConnection:
    """Singleton database connection manager."""

    _instance: Optional[Memgraph] = None
    _config: Optional[DatabaseConfig] = None

    @classmethod
    def configure(cls, config: DatabaseConfig) -> None:
        """
        Configure the database connection.

        Args:
            config: Database configuration
        """
        cls._config = config
        cls._instance = None  # Reset instance to force reconnection

    @classmethod
    def get_instance(cls) -> Memgraph:
        """
        Get or create database connection instance.

        Returns:
            Memgraph connection instance

        Raises:
            RuntimeError: If connection is not configured
        """
        if cls._instance is None:
            if cls._config is None:
                # Try to load from environment
                cls._config = DatabaseConfig.from_env()

            cls._instance = Memgraph(
                host=cls._config.host,
                port=cls._config.port,
                username=cls._config.username,
                password=cls._config.password,
                encrypted=cls._config.encrypted,
                lazy=cls._config.lazy,
            )

        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the connection (useful for testing)."""
        cls._instance = None
        cls._config = None


# Convenience function for getting database connection
def get_db() -> Memgraph:
    """
    Get the database connection instance.

    Returns:
        Memgraph connection instance
    """
    return DatabaseConnection.get_instance()
