---
name: df:db-reset
description: Reset the graph database by clearing all nodes, relationships, indexes, and constraints.
---

Usage: /df:db-reset

This is useful during development when the database gets polluted with test data.

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
