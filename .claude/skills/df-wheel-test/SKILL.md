---
name: df-wheel-test
description: Run the full Explorer end-to-end wheel test against a real LLM provider and Memgraph. Use to verify the Explorer produces valid wheels after changes to the exploration pipeline, transformations, or synthesis.
disable-model-invocation: true
allowed-tools: Bash(poetry run pytest *)
---

Usage: `/df-wheel-test`

Runs the Explorer wheel end-to-end test with a real LLM provider. Requires Memgraph running (`docker compose -f docker-compose.test.yml up -d`) and provider credentials in `.env`.

```bash
poetry run pytest "tests/test_agents_e2e.py::TestExplorerEndToEnd::test_explorer_produces_wheels" --real-llm -v -s --tb=short
```
