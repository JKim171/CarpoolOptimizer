.PHONY: setup test lint fmt typecheck check db

setup:
	python3 -m venv .venv
	.venv/bin/pip install -q -U pip -r requirements-dev.txt -e packages/domain

test:
	.venv/bin/pytest

lint:
	.venv/bin/ruff check .
	.venv/bin/ruff format --check .

fmt:
	.venv/bin/ruff format . && .venv/bin/ruff check --fix .

typecheck:
	.venv/bin/mypy packages/domain/src

check: lint typecheck test

db:
	docker compose up -d postgres
