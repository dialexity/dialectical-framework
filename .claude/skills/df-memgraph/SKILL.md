---
name: df-memgraph
description: Manage the test Memgraph container (start/stop/restart/status/logs/clear/wipe) via docker-compose.test.yml. Use when graph tests need the DB up, data cleared, a stuck lock cleared, or the volume fully wiped.
disable-model-invocation: true
allowed-tools: Bash(docker compose *), Bash(poetry run python *)
---

Usage: `/df-memgraph [start|stop|restart|status|logs|clear|wipe]` (default: `status`)

Controls the test Memgraph + Memgraph Lab containers defined in `docker-compose.test.yml`.
Run from the repo root. Graph tests require Memgraph running; Memgraph is a test-only
dependency, never a production one.

Pick the command matching the argument. If no argument is given, run `status`.

### `start` — bring the DB up
Starts Memgraph (bolt on `127.0.0.1:7687`) and Memgraph Lab (http://localhost:3000).
Idempotent — safe to run when already up.
```bash
docker compose -f docker-compose.test.yml up -d
```

### `stop` — stop the containers, keep data
Stops and removes the containers but **keeps** the `mg_lib` volume, so data survives.
```bash
docker compose -f docker-compose.test.yml down
```

### `restart` — clear a stuck lock, keep data
Use this when a `pytest` run was `pkill -9`'d mid-test and the autouse `cleanup_graph_db`
fixture's `DETACH DELETE` lock is stuck (symptom: graph tests hang/deadlock). Restart
clears the lock but does **not** clear the data (the `mg_lib` volume persists).
```bash
docker compose -f docker-compose.test.yml restart
```

### `status` — is it up? (default)
```bash
docker compose -f docker-compose.test.yml ps
```

### `logs` — recent Memgraph logs
```bash
docker compose -f docker-compose.test.yml logs --tail 80 memgraph
```

### `clear` — wipe data only, container stays up
Fastest reset: clears all nodes, relationships, indexes, and constraints via cypher
while the container keeps running (no volume destroy, no restart). Use during
development when Memgraph gets polluted with test data. Requires the DB to be up.
```bash
poetry run python -c "
from gqlalchemy import Memgraph

db = Memgraph(host='127.0.0.1', port=7687)

# Drop all constraints first
print('Dropping constraints...')
for row in db.execute_and_fetch('SHOW CONSTRAINT INFO'):
    for prop in row['properties']:
        query = f\"DROP CONSTRAINT ON (n:{row['label']}) ASSERT n.{prop} IS UNIQUE\"
        print(f'  {query}')
        db.execute(query)

# Drop all indexes
print('Dropping indexes...')
for row in db.execute_and_fetch('SHOW INDEX INFO'):
    for prop in row['property']:
        query = f\"DROP INDEX ON :{row['label']}({prop})\"
        print(f'  {query}')
        db.execute(query)

# Delete all nodes and relationships
print('Deleting all nodes and relationships...')
result = list(db.execute_and_fetch('MATCH (n) DETACH DELETE n RETURN count(n) as deleted'))
deleted = result[0]['deleted'] if result else 0
print(f'  Deleted {deleted} nodes')

print()
print('Database reset complete.')
"
```

### `wipe` — destroy the volume and start fresh
Full reset: tears down the containers **and** deletes the persistent `mg_lib` volume
(all data gone), then brings a clean DB back up. Use when stale leftover nodes cause
spurious failures in unrelated tests and a plain `clear` isn't enough (e.g. the stuck
lock persists or the container itself is wedged).
```bash
docker compose -f docker-compose.test.yml down -v && docker compose -f docker-compose.test.yml up -d
```

---

**Notes:**
- Memgraph Lab (visual browser) is at http://localhost:3000 once `start` completes.
- **Only one graph-test run at a time** — concurrent pytest processes against the same
  Memgraph deadlock on the cleanup fixture.
- Reset ladder, cheapest first: `clear` (data only, container up) → `restart` (clears a
  stuck lock, keeps data) → `wipe` (destroys the volume, fresh DB).
