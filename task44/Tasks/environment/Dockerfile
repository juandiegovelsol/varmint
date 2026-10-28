# =============================================================================
# fossasia/eventyay — Harbor task image (DONOR RECIPE)
#
# eventyay is a single Django 6 monolith (a merge of pretix + pretalx + video)
# living in the repo sub-directory `app/`.  Everything below is written so that
# retargeting the image at a different commit of the SAME repo requires editing
# ONLY the two 40-hex SHAs on the `git fetch` / `git checkout` line — which is
# exactly what tools/harvest_m2.py:retarget_dockerfile() does.
#
# Design rules honoured here:
#   * base image tracks the repo's own pin: `requires-python = ">=3.12, <3.13"`
#     and app/Dockerfile uses python:3.12-slim-trixie.
#   * the repo is fetched with a SHALLOW single-SHA fetch (no full clone: the
#     repo is ~320 MB of history), then `.git` is destroyed and re-initialised
#     as ONE commit tagged `harbor_base`, so the agent cannot read the future.
#   * EVERY test dependency is installed AT BUILD TIME.  The verify run is
#     OFFLINE — nothing may be downloaded there.
#   * eventyay only supports PostgreSQL (django.contrib.postgres, JSONB, ARRAY),
#     so a real PostgreSQL cluster is initialised INSIDE the image at build time
#     and started from test.sh over the loopback interface at verify time.
#     No network egress is involved.
# =============================================================================
FROM python:3.12-slim-trixie

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LANG=C.UTF-8

# --- system dependencies ------------------------------------------------------
# git            : fetch + the harbor_base tag machinery used by test.sh
# build-essential/
#   libffi/ssl/  : source builds for the few deps without an aarch64 wheel
#   xml/xslt/jpeg/
#   freetype/zlib
# gettext        : `manage.py compilemessages`; several i18n tests read .mo files
# libpq-dev      : psycopg build headers
# postgresql*    : eventyay has NO sqlite fallback — the DB must live in-image
# poppler-utils  : pdf2image (invoice / badge PDF tests)
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl git \
      build-essential pkg-config \
      gettext \
      libffi-dev libssl-dev zlib1g-dev libjpeg-dev libfreetype6-dev \
      libxml2-dev libxslt1-dev \
      libpq-dev postgresql postgresql-client \
      poppler-utils \
      procps \
 && rm -rf /var/lib/apt/lists/*

# uv is the repo's own package manager (app/uv.lock is authoritative).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# --- source tree at the base commit ------------------------------------------
# Shallow single-SHA fetch, then history is erased and rebuilt as one commit so
# that `git checkout harbor_base -- <path>` works in test.sh while the agent can
# see neither the fixing PR nor any future work.
#
# >>> THE ONLY PER-TASK LINE IN THIS FILE IS THE SHA BELOW. <<<
WORKDIR /app
RUN git init -q /app \
 && git -C /app remote add origin https://github.com/fossasia/eventyay \
 && git -C /app fetch --depth 1 --no-tags origin 3be6b7a2412e081397f1d3ded87760b0286bccd6 \
 && git -C /app checkout 3be6b7a2412e081397f1d3ded87760b0286bccd6 \
 && rm -rf /app/.git \
 && git -C /app init -q -b main \
 && git -C /app -c user.email=h@l -c user.name=h add -A \
 && git -C /app -c user.email=h@l -c user.name=h commit -q -m base \
 && git -C /app tag harbor_base

# --- python environment -------------------------------------------------------
# The python project root is /app/app (pyproject.toml + uv.lock live there).
# The venv is placed OUTSIDE the work tree so that a `git clean` inside /app can
# never delete it.  The project itself is installed EDITABLE (uv's default) so
# the agent's edits under /app/app/eventyay take effect with no reinstall.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH
WORKDIR /app/app
# Test-only deps are NOT installed into the agent's environment. They are
# downloaded into uv's cache at build time so that test.sh can install them
# OFFLINE at verify time, keeping pytest out of the image the agent sees.
RUN uv sync --frozen --all-extras --group test \
 && uv sync --frozen --all-extras \
 && python -c "import django; print(django.get_version())"

# Compile the shipped translations: several eventyay tests assert on translated
# strings, and `manage.py compilemessages` is part of the repo's own `make all`.
RUN python manage.py compilemessages -x en 2>/dev/null || true

# --- in-image PostgreSQL ------------------------------------------------------
# Cluster is created (and the application database pre-created) at BUILD time so
# that verify time only has to `pg_ctl start` — an offline, loopback-only op.
# `-A trust` is safe: the container is single-tenant and unreachable.
ENV PGDATA=/var/lib/postgresql/harbor \
    EVY_POSTGRES_HOST=127.0.0.1 \
    EVY_POSTGRES_PORT=5432 \
    EVY_POSTGRES_USER=postgres \
    EVY_POSTGRES_PASSWORD=postgres \
    EVY_POSTGRES_DB=pretix
# /logs must exist before the cluster is first started: the starter script points
# the server log at /logs/postgres.log.
RUN mkdir -p /logs "$PGDATA" /var/run/postgresql \
 && chmod 777 /logs \
 && chown -R postgres:postgres "$PGDATA" /var/run/postgresql

# --- running as `postgres` on a daemon that ships / as 0750 -------------------
# PostgreSQL REFUSES to run as uid 0: initdb and the postmaster both abort on
# `geteuid() == 0` and there is no override flag, so every cluster step below has
# to run as the `postgres` user.  That is ordinarily trivial, but some daemons
# hand the build a rootfs whose ROOT DIRECTORY is 0750:
#
#     drwxr-x---  1 root root  /
#
# `/` is then untraversable for every non-root uid, so such a process dies before
# it reaches main(), with the loader unable to resolve libc:
#
#     /bin/sh: error while loading shared libraries: libc.so.6:
#              cannot open shared object file: Permission denied
#
# `chmod a+rx /` repairs it — but a mode change on the rootfs ROOT DIRECTORY is
# not captured in a layer diff, so it is reverted at the start of the next RUN.
# (Verified: `RUN chmod 0750 / && ls -ld /` followed by `RUN ls -ld /` prints
# 0750 and then 0755.)  Two consequences, both load-bearing:
#
#   * the repair must happen in the SAME layer as the non-root process, so a bare
#     `USER postgres` stanza cannot work here no matter what precedes it;
#   * the shipped image keeps whatever `/` the daemon gives it, so the runtime
#     starter has to repeat the repair before it drops privileges.
#
# Hence this one helper, used by both the build steps below and by
# harbor_pg_start at verify time.  It is a no-op on a normal daemon.
RUN printf "%s\n" \
    "#!/bin/sh" \
    "# Run \"\$@\" as the postgres user.  Repairs an untraversable / first: see" \
    "# the long comment in the Dockerfile for why this cannot be a USER stanza." \
    "set -eu" \
    "chmod a+rx /" \
    "exec setpriv --reuid=postgres --regid=postgres --clear-groups \"\$@\"" \
    > /usr/local/bin/harbor_as_postgres && chmod +x /usr/local/bin/harbor_as_postgres

# Preflight: prove non-root execution works through the same path the cluster
# steps use, and say so plainly BEFORE initdb muddies the log.  A failure here
# with `/` already world-traversable in the listing means the restriction is
# imposed by the daemon or an LSM rather than by file modes — that is not fixable
# from this Dockerfile and belongs with whoever maintains the sandbox.
RUN echo "== non-root preflight ==" \
 && id postgres \
 && ls -ld / /usr/lib /usr/share /var/lib/postgresql \
 && if harbor_as_postgres /bin/sh -c 'echo NONROOT_OK'; then \
      echo "PREFLIGHT: non-root execution works"; \
    else \
      echo "NONROOT_STILL_BROKEN: cannot execute as postgres on this daemon." >&2; \
      echo "  PostgreSQL refuses to run as uid 0, so this image cannot build here." >&2; \
      echo "  Report the modes printed above to the sandbox maintainers." >&2; \
      exit 1; \
    fi

RUN harbor_as_postgres "$(ls -d /usr/lib/postgresql/*/bin)/initdb" \
      -D "$PGDATA" -A trust -U postgres --encoding=UTF8 --locale=C

# Server tuning lives in postgresql.conf rather than in `pg_ctl -o`, so that the
# start command needs no nested quoting anywhere.  fsync/full_page_writes off is
# safe and much faster: the cluster is throwaway, recreated with every container.
#
# The extensions are installed into template1 as well as into the application
# database: pytest-django creates `test_pretix` from template1, and eventyay's
# test settings DISABLE MIGRATIONS (tests/testutils/settings.py) so the schema is
# built with `--run-syncdb` and the CreateExtension migrations never execute.
# Without pg_trgm the whole tickets suite dies on
# `operator class "gin_trgm_ops" does not exist`.
RUN printf "%s\n" \
    "listen_addresses = '127.0.0.1'" \
    "port = 5432" \
    "fsync = off" \
    "full_page_writes = off" \
    "synchronous_commit = off" \
    "max_connections = 100" \
    >> "$PGDATA/postgresql.conf"
RUN PGBIN="$(ls -d /usr/lib/postgresql/*/bin)" \
 && harbor_as_postgres "$PGBIN/pg_ctl" -D "$PGDATA" -l /logs/postgres.log -w start \
 && harbor_as_postgres psql -h 127.0.0.1 -U postgres -c "CREATE DATABASE pretix" \
 && for _ext in pg_trgm btree_gin btree_gist unaccent citext hstore pgcrypto; do \
      harbor_as_postgres psql -q -h 127.0.0.1 -U postgres -d template1 -c "CREATE EXTENSION IF NOT EXISTS $_ext"; \
      harbor_as_postgres psql -q -h 127.0.0.1 -U postgres -d pretix    -c "CREATE EXTENSION IF NOT EXISTS $_ext"; \
    done \
 && harbor_as_postgres "$PGBIN/pg_ctl" -D "$PGDATA" -w stop

# One-line starter that every eventyay test.sh calls before pytest.
# Idempotent, offline, and waits until the server actually accepts connections.
# `\$` keeps the expansion for RUN TIME instead of build time.
RUN printf "%s\n" \
    "#!/bin/sh" \
    "# Start the in-image PostgreSQL cluster (offline; loopback only). Idempotent." \
    "set -u" \
    "PGBIN=\$(ls -d /usr/lib/postgresql/*/bin)" \
    "mkdir -p /var/run/postgresql /logs" \
    "chown postgres:postgres /var/run/postgresql" \
    "# The server must run as user postgres: PostgreSQL aborts on euid 0, and" \
    "# harbor_as_postgres repairs an untraversable / on the way.  Fail loudly if" \
    "# even that cannot execute, rather than after a 60-second pg_isready wait." \
    "harbor_as_postgres /bin/sh -c true || {" \
    "  echo \"FATAL: cannot execute as postgres in this container; see \\\`ls -ld /\\\`.\" >&2" \
    "  exit 1" \
    "}" \
    "harbor_as_postgres \$PGBIN/pg_isready -q -h 127.0.0.1 -p 5432 && exit 0" \
    "harbor_as_postgres \$PGBIN/pg_ctl -D \$PGDATA -l /logs/postgres.log -w start || true" \
    "for _ in \$(seq 1 60); do harbor_as_postgres \$PGBIN/pg_isready -q -h 127.0.0.1 -p 5432 && exit 0; sleep 1; done" \
    "echo \"postgres did not come up\" >&2" \
    "exit 1" \
    > /usr/local/bin/harbor_pg_start && chmod +x /usr/local/bin/harbor_pg_start

# --- harness plumbing ---------------------------------------------------------
# Visual evidence from the issue, readable by the agent at /app/.harbor_assets/.
# tests/ and solution/ are intentionally NOT baked in — the harness mounts them
# at verify time.
RUN mkdir -p /logs /app/.harbor_assets
COPY assets/ /app/.harbor_assets/

WORKDIR /app
CMD ["bash"]
