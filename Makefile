.PHONY: setup test lint fmt typecheck check db migrate revision api \
        web-setup web web-check openapi

setup: web-setup hooks
	python3 -m venv .venv
	.venv/bin/pip install -q -U pip -r requirements-dev.txt -e packages/domain -e 'apps/api[test]'

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
	.venv/bin/mypy packages/domain/src apps/api/src

# prettier, eslint, the generated-types drift check, and tsc.
web-check:
	cd apps/web && npm run check

check: lint typecheck test web-check

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
