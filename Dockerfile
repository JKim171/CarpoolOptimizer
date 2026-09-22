# The API image, built by CI for arm64 (the instance is Graviton) and deployed by digest
# (docs/design.md 10.1). It also carries deploy/, so the configuration a deploy runs with always
# comes from the same build as the code.
#
# Nothing secret is ever baked in: the package is public, so the instance pulls it without a
# registry credential. Secrets arrive through the environment at run time.

FROM python:3.13-slim-trixie@sha256:8d9d0b8bcf6506481eae4907c18f5e3e7902e629f5f6d684f9e7c32e85e3ddf0

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Every third-party package, by exact version and hash. --no-deps because the lock is already the
# complete closure: anything it does not list is not installed, rather than resolved from PyPI.
COPY requirements.txt .
RUN pip install --require-hashes --no-deps -r requirements.txt

# The two local packages run from source on PYTHONPATH rather than being pip-installed. Installing
# them would fetch an unpinned setuptools to build them, which is the one download the lock cannot
# cover.
COPY packages/domain/src packages/domain/src
COPY apps/api/src apps/api/src
COPY apps/api/alembic.ini apps/api/alembic.ini
COPY apps/api/alembic apps/api/alembic
COPY deploy deploy
ENV PYTHONPATH=/app/packages/domain/src:/app/apps/api/src

RUN useradd --system --uid 10001 --no-create-home app
USER app

EXPOSE 8000

# One process: the rate-limit counters live in its memory, so a second worker would give every
# client a second allowance (docs/design.md 10.1). --proxy-headers trusts X-Forwarded-For only from
# the addresses in FORWARDED_ALLOW_IPS, which deploy/compose.yml sets to Caddy's; unset, uvicorn
# trusts 127.0.0.1 alone, so a missing value fails closed.
CMD ["uvicorn", "carpool_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
