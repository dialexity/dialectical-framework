---
name: df:wheel-test
description: Run the full Explorer end-to-end wheel test (requires real LLM and Memgraph).
---

Run the Explorer wheel e2e test with a real LLM provider.

```bash
poetry run pytest "tests/test_agents_e2e.py::TestExplorerEndToEnd::test_explorer_produces_wheels" --real-llm -v -s --tb=short
```
