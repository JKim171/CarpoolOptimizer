.PHONY: setup hooks test lint fmt typecheck check audit lock db migrate revision api \
        web-setup web web-check openapi demo bench bench-report

# Runtime dependencies come from the hashed lock and the benchmark-only ones from theirs, the local
# packages are installed on top without resolving anything, and the dev tools last. CI installs in
# the same steps.
setup: web-setup hooks
	python3 -m venv .venv
	.venv/bin/pip install -q -U pip
	.venv/bin/pip install -q --require-hashes -r requirements.txt
	.venv/bin/pip install -q --require-hashes -r requirements-bench.txt
	.venv/bin/pip install -q --no-deps -e packages/domain -e apps/api -e packages/bench
	.venv/bin/pip install -q -r requirements-dev.txt

# .git/hooks is not committed, so a fresh clone has no hooks until this runs.
hooks:
	git config core.hooksPath .githooks

web-setup:
	cd apps/web && npm ci
	@test -f apps/web/.env.local || cp apps/web/.env.example apps/web/.env.local

test:
	.venv/bin/pytest

lint:
	.venv/bin/ruff check .
	.venv/bin/ruff format --check .

fmt:
	.venv/bin/ruff format . && .venv/bin/ruff check --fix .

typecheck:
	.venv/bin/mypy packages/domain/src apps/api/src packages/bench/src

# prettier, eslint, the generated-types drift check, and tsc.
web-check:
	cd apps/web && npm run check

check: lint typecheck test web-check

# Known advisories against the pinned runtime and benchmark dependencies. Needs the network, so it
# runs in CI and on demand rather than inside `check`.
audit:
	.venv/bin/pip-audit --disable-pip --require-hashes -r requirements.txt
	.venv/bin/pip-audit --disable-pip --require-hashes -r requirements-bench.txt

# Re-resolve both locks after changing a dependency in a pyproject.toml. Existing pins are kept;
# `make lock LOCK_FLAGS=--upgrade` moves every pin to the newest release the ranges allow. The
# benchmark lock is constrained by the runtime one, so it is compiled second.
lock:
	.venv/bin/pip-compile -q --generate-hashes --strip-extras $(LOCK_FLAGS) \
	  --unsafe-package carpool-api --unsafe-package carpool-domain \
	  -o requirements.txt requirements.in
	.venv/bin/pip-compile -q --generate-hashes --strip-extras $(LOCK_FLAGS) \
	  --unsafe-package carpool-bench --unsafe-package carpool-domain \
	  -o requirements-bench.txt requirements-bench.in

db:
	docker compose up -d --build postgres

# Alembic runs from the repository root so that .env is on the path it looks for; alembic.ini
# resolves its script_location absolutely, so the -c is all it needs.
migrate:
	.venv/bin/alembic -c apps/api/alembic.ini upgrade head

revision:
	.venv/bin/alembic -c apps/api/alembic.ini revision -m "$(m)"

api:
	.venv/bin/uvicorn carpool_api.main:app --reload --port 8000

web:
	cd apps/web && npm run dev

# Regenerate the API contract and the TypeScript types built from it. Run this after any change to
# a route or a schema; test_openapi_contract.py fails the build when it is stale. DATABASE_URL is
# supplied here only because building the app reads settings -- nothing in this target connects.
openapi:
	DATABASE_URL=postgresql+asyncpg://unused/unused \
	  .venv/bin/python -m carpool_api.contract apps/web/lib/api/openapi.json
	cd apps/web && npm run types:generate

# Regenerate the example event behind /demo. Run this after changing the solver, the generator or a
# solution schema; test_demo.py fails the build when the committed file no longer matches.
demo:
	DATABASE_URL=postgresql+asyncpg://unused/unused \
	  .venv/bin/python -m carpool_api.demo apps/web/lib/demo/event.json

# The benchmark grid (docs/design.md 8.5): about half an hour, most of it CP-SAT proving the
# 50-person instances optimal. Commit the results it writes, then `make bench-report`.
bench:
	.venv/bin/python -m carpool_bench run --out docs/benchmarks/results.json

bench-report:
	.venv/bin/python -m carpool_bench report docs/benchmarks/results.json \
	  --out docs/benchmarks/README.md
