---
name: local-postgres-for-tests
description: How to bring up a local Postgres so pytest can run in this container
metadata: 
  node_type: memory
  type: reference
  originSessionId: 38d96b65-b076-440b-81e8-a8c81abbf3ff
  modified: 2026-08-16T15:51:48.617Z
---

`pytest` needs Postgres on `127.0.0.1:5432`, DB name `eventyay-db` (see `app/eventyay/config/settings.py`). No cluster runs by default. Bootstrap:

1. `usermod -aG root postgres` — `/` is `drwxr-x---`, so the postgres user otherwise can't traverse it to load libs.
2. As postgres (root can't run initdb/postgres): `setpriv --reuid postgres --regid postgres --groups root /usr/lib/postgresql/17/bin/initdb -D /tmp/pgdata -U postgres`
3. Socket in `/tmp` is blocked; use a dedicated owned dir: `mkdir /tmp/pgrun && chown postgres /tmp/pgrun`, then `setpriv ... pg_ctl -D /tmp/pgdata -o "-p 5432 -k /tmp/pgrun -c listen_addresses=127.0.0.1" -l /tmp/pg.log start` (log file must be pre-created and chowned to postgres).
4. `createdb`/`psql -h 127.0.0.1 -U postgres -c 'CREATE DATABASE "eventyay-db";'`
5. Enable trgm: `psql ... -d template1 -c 'CREATE EXTENSION IF NOT EXISTS pg_trgm;'` (migrations need `gin_trgm_ops`).

Run: `cd app && python -m pytest tests/...`. Note ruff/uvx have no network here. See [[talk-test-suite-conftest-drift]].
