.PHONY: setup test lint fmt typecheck check db migrate revision api

setup:
	python3 -m venv .venv
	.venv/bin/pip install -q -U pip -r requirements-dev.txt -e packages/domain -e 'apps/api[test]'

test:
	.venv/bin/pytest

lint:
	.venv/bin/ruff check .
	.venv/bin/ruff format --check .

fmt:
	.venv/bin/ruff format . && .venv/bin/ruff check --fix .

typecheck:
	.venv/bin/mypy packages/domain/src apps/api/src

check: lint typecheck test

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
