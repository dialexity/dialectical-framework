# Dialectical Framework
A dialectical framework for augmented intelligence. AI reasoning powered with dialectics supports humans in: system optimization (psychology, engineering, business, politics, etc.); dispute resolution (mediation, conflicts, negotiations, etc.); decision-making (dilemmas, challenging situations, win-win, etc.).

## Use Cases
- Extract 1 concept, primary thesis
  - Dialectical analysis of a single concept
- Extract 2 opposing theses
  - Close the wheel with Ac and Re
  - Reciprocal solution
- Extract 2 theses with circular causation 
  - Compose into a wheel
  - Reciprocal solutions
- Extract 3 theses with circular causation
  - Compose X wheels
  - Estimate each wheel's probability
- Extract 4 theses with circular causation
  - Compose X wheels
  - Estimate each wheel's probability

## Development

### Setup

This project uses Poetry for dependency management. To get started:

1. Make sure you have Poetry installed:
```bash
curl -sSL https://install.python-poetry.org | python3 -
```

2. Install dependencies:
```bash
poetry install
```

3. Activate the virtual environment:
```bash
poetry shell
```

- Run tests: `pytest`
- Format code: `black .`
- Sort imports: `isort .`