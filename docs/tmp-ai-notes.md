I'll explore the project structure first to better understand the dialectical framework.Based on the comprehensive code review and the existing README.md, I'll create a detailed description for your NOTES.md file that serves as a reference point for AI to understand the dialectical framework project:

# NOTES.md - Dialectical Framework Project Reference

## Project Overview

The **Dialectical Framework** is a sophisticated Python library designed to transform natural language text into structured dialectical analysis through the creation of **Dialectical Wheels (DWs)**. The framework automatically extracts thesis-antithesis relationships, reveals systemic tensions, and maps transformation pathways toward synthesis.

## Core Architecture & Data Structures

### 1. Dialectical Component (`dialectical_component.py`)
The atomic unit of the framework - represents a single statement, concept, or idea with an alias identifier. Components can be compared for semantic similarity and serve as building blocks for larger structures.

### 2. Wheel Segment (`wheel_segment.py`)
A "slice" of the dialectical wheel containing three dialectical components:
- **T**: The main thesis
- **T+**: Positive side/enhancement of the thesis  
- **T-**: Negative side/degradation of the thesis

Supports flexible field access through both field names and aliases (e.g., accessing "t" field via "T" alias).

### 3. Wisdom Unit (`wisdom_unit.py`)
The fundamental "molecule" of dialectical analysis, extending WheelSegment to include antithesis components:
- **T, T+, T-**: Thesis and its positive/negative aspects
- **A, A+, A-**: Antithesis and its positive/negative aspects

Represents complementary opposing relationships and includes methods to swap thesis/antithesis positions and extract individual segments.

### 4. Wheel (`wheel.py`)
The complete dialectical structure composed of multiple wisdom units arranged in a circular pattern. Manages the relationships between segments and provides methods for:
- Accessing wisdom units by position/reference
- Spinning the wheel to different orientations
- Managing cycles and spiral progressions
- Converting to chain-of-thought representations

### 5. Transitions (`transition*.py`)
Represent transformation pathways between dialectical components:
- **Transition**: Base class for component-to-component transformations
- **SymmetricalTransition**: Bidirectional transformations with Action (Ac) and Reflection (Re) components
- **TransitionSegmentToSegment**: Transformations between wheel segments

### 6. Directed Graph (`directed_graph.py`)
Manages the network of transitions between dialectical components, supporting:
- Path traversal and cycle detection
- Transition storage and retrieval by source/target aliases
- Graph analysis including DFS traversal with cycle detection

### 7. Spiral (`spiral.py`)
Represents the dynamic progression through dialectical transformations over time, built on the directed graph structure.

## AI-Powered Analysis Components

### Dialectical Reasoner (`synthesist/dialectical_reasoner.py`)
Abstract base class for AI-powered dialectical analysis featuring:
- **Thesis Extraction**: Identifies central ideas from input text
- **Antithesis Generation**: Creates dialectical oppositions
- **Component Refinement**: Generates positive/negative aspects of each component
- Uses prompt templates and LLM integration via Mirascope framework

### Strategic Consultants
Specialized AI components for different types of dialectical analysis:
- **ThinkActionReflection**: Generates Action-Reflection transition pairs
- **ThinkReciprocalSolution**: Creates reciprocal solution pathways
- **ThinkConstructiveConvergence**: Develops convergence strategies

### Wheel Builders (`synthesist/factories/`)
Factory pattern implementations for constructing dialectical wheels:
- **ConfigWheelBuilder**: Configuration management for wheel construction
- **WheelBuilder**: Base builder with dialectical reasoner integration
- **Decorator Pattern**: Various decorators for adding transition calculations
  - **DecoratorActionReflection**: Adds action-reflection transitions
  - **DecoratorReciprocalSolution**: Adds reciprocal solution transitions

## Key Design Patterns

### 1. Builder Pattern
Wheel construction uses the builder pattern with decorator extensions for adding different types of analysis capabilities.

### 2. Template Method Pattern
Strategic consultants use template methods for consistent AI-powered analysis workflows.

### 3. Alias System
Components use a flexible alias system allowing access via semantic names (T, T+, A-) or field names.

### 4. Async AI Integration
All AI-powered components use async/await patterns for efficient LLM communication.

## Core Capabilities

### Text-to-Wheel Transformation
1. **Input Processing**: Natural language text analysis
2. **Thesis Extraction**: AI identifies central concepts
3. **Dialectical Expansion**: Generation of antitheses and positive/negative aspects
4. **Wheel Construction**: Assembly of components into structured wheels
5. **Transition Analysis**: AI-generated transformation pathways

### Analysis Features
- **Blind Spot Detection**: Identification of overlooked perspectives
- **Polarity Mapping**: Visualization of opposing forces
- **Synthesis Pathways**: Routes toward resolution and integration
- **Systemic Insights**: Revelation of hidden relationships and leverage points

### Validation & Quality Control
The framework includes validation components to ensure dialectical consistency and logical coherence of generated structures.

## Technical Foundation

- **Language**: Python 3.11.8
- **Package Management**: Poetry
- **AI Integration**: Mirascope framework for LLM communication
- **Data Modeling**: Pydantic for structured data validation
- **Architecture**: Modular, extensible design with clear separation of concerns

## Usage Context

The framework is designed for:
- **Systems Analysis**: Understanding complex system dynamics
- **Decision Support**: Revealing hidden considerations in strategic decisions  
- **Ethical Modeling**: Mapping moral and ethical dimensions
- **Narrative Analysis**: Extracting dialectical structures from stories and texts
- **Conflict Resolution**: Understanding opposing perspectives and synthesis paths

This framework represents a sophisticated approach to automated dialectical reasoning, combining classical philosophical concepts with modern AI capabilities to provide deep analytical insights into complex systems and narratives.