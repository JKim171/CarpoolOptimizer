# Postgres 16 with PostGIS, native on arm64 (Apple Silicon, Graviton) and amd64 (CI runners).
#
# postgis/postgis publishes amd64 only, so it runs under emulation on both arm64 machines
# (docs/design.md 10.1). The official postgres image already carries the PostgreSQL apt repository,
# whose PostGIS package is built for both architectures.
#
# The image only makes the extension available. `CREATE EXTENSION postgis` belongs to the schema
# migrations, so every database -- development, production, testcontainers -- gets it the same way.
FROM postgres:16-trixie

RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-16-postgis-3 \
    && rm -rf /var/lib/apt/lists/*
