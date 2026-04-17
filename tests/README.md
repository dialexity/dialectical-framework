# Testing Guide

## Running Graph Tests

Graph tests require Memgraph to be running. Memgraph is only needed for testing, not as a production dependency.

### Quick Start

1. **Start Memgraph using Docker:**
   ```bash
   docker compose -f docker-compose.test.yml up -d
   ```

2. **Run the tests:**
   ```bash
   poetry run pytest tests/test_graph.py -v
   ```

   **✅ SAFETY**: Tests only delete nodes labeled with `:___DIALEXITY_TEST___`
   - Production data is safe - tests can run alongside real data
   - All test nodes are automatically labeled by the test fixture
   - Only labeled test data is cleaned up before/after each test

3. **Access Memgraph Lab (visual interface):**
   Open http://localhost:3000 in your browser to visualize the graph database.

4. **Stop Memgraph:**
   ```bash
   docker compose -f docker-compose.test.yml down
   ```

### What Happens If Memgraph Isn't Running?

Tests will automatically skip with a helpful message:
```
SKIPPED - Memgraph is not available. Run: docker-compose -f docker-compose.test.yml up -d
```

### CI/CD Integration

For CI environments, you can add Memgraph as a service:

**GitHub Actions example:**
```yaml
services:
  memgraph:
    image: memgraph/memgraph:latest
    ports:
      - 7687:7687
```

## Test Structure

- `conftest.py` - Shared fixtures including Memgraph connection
- `test_graph.py` - Graph structure tests (Perspective, components, relationships)

## Notes

- Each test runs in a clean database (cleared before/after)
- The `db` fixture automatically handles connection and cleanup
- Memgraph runs in-memory mode for fast testing
