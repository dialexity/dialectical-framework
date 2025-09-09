# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

This is a Python project using Poetry for dependency management:

- **Install dependencies**: `poetry install`
- **Run tests**: `poetry run pytest` or `pytest` if in activated environment
- **Format code**: `poetry run black src/ tests/`
- **Sort imports**: `poetry run isort src/ tests/`
- **Remove unused imports**: `poetry run autoflake --in-place --remove-all-unused-imports --recursive src/ tests/`
- **Activate virtual environment**: `poetry shell`
- **Build package**: `poetry build`

## Core Architecture

The Dialectical Framework implements a semantic graph system for dialectical reasoning, structured as a wheel metaphor:

### Core Components

- **Wheel**: The main container composed of segments, representing a complete dialectical system
- **WheelSegment**: Individual "slices" of the wheel, each containing dialectical components
- **WisdomUnit**: A half-wheel structure containing thesis-antithesis pairs with validation constraints
- **DialecticalComponent**: Basic building blocks representing statements/concepts with aliases (T, A, T+, A-, etc.)
- **Transition**: Rules for moving between segments, enabling synthesis pathways

### Key Domain Objects

- **Cycle**: Represents cyclical patterns in dialectical reasoning
- **Spiral**: Advanced cycle with transformational properties
- **Transformation**: Rules for converting dialectical components
- **Rationale**: Explanatory context for dialectical relationships

### Architectural Patterns

1. **Protocol-Based Design**: Uses Python protocols (`Assessable`, `Ratable`, `HasBrain`) for flexible composition
2. **Circular Dependency Resolution**: The `__init__.py` file carefully orders imports and rebuilds Pydantic models to resolve circular references
3. **AI Integration**: Heavy use of Mirascope for LLM interactions, with Brain abstraction for model switching
4. **Dependency Injection**: Uses `dependency-injector` for service composition

### Module Structure

- `synthesist/`: Core reasoning engines (polarity, causality, concepts)
- `analyst/`: Analysis and validation tools (domain objects, consultants, decorators)
- `protocols/`: Interface definitions for extensibility
- `ai_dto/`: Data transfer objects for AI interactions
- `utils/`: Utility functions and helpers
- `validator/`: Validation and checking logic

## Environment Configuration

Required environment variables:
- `DIALEXITY_DEFAULT_MODEL`: Default LLM model (e.g., "gpt-4")
- `DIALEXITY_DEFAULT_MODEL_PROVIDER`: Model provider ("openai", "anthropic", etc.)

Store these in a `.env` file in the project root.

## Testing

Tests are located in `tests/` directory. The project uses pytest with asyncio support enabled. Key test files:
- `test_synthesist.py`: Core reasoning engine tests
- `test_analyst.py`: Analysis functionality tests
- `test_wu_construction.py`: Wisdom Unit construction tests
- `conftest.py`: Shared test configuration

## Development Notes

- **Pydantic Models**: Many classes inherit from Pydantic models for validation and serialization
- **Async Support**: The framework supports both sync and async operations
- **Model Rebuilding**: Due to circular dependencies, Pydantic models require explicit rebuilding in `__init__.py`
- **AI Brain Abstraction**: The `Brain` class provides a unified interface for different LLM providers
- **Contextual Fidelity**: The system tracks probability and confidence propagation through dialectical structures
- Scoring architecture is described in scoring.md