# CodeWeave Makefile
# 使用正确的 flag 封装 uv 命令，以兼容工作区（Windows 上 uv 0.11.x 的特殊行为）

.PHONY: sync install test test-backend test-integration lint format clean dev-up dev-down worker beat migrate migrate-new migrate-down

sync:
	uv sync --all-packages

install: sync

test:
	cd backend && uv run pytest -v --tb=short

test-integration:
	cd backend && DATABASE_URL=postgresql://codeweave:codeweave_dev@localhost:5432/codeweave uv run pytest tests/integration/ -v

lint:
	cd backend && uv run ruff check src tests

format:
	cd backend && uv run ruff format src tests

dev-up:
	docker compose up -d
	@echo "Waiting for postgres..."
	@powershell -Command "Start-Sleep -Seconds 3"
	@docker exec codeweave-postgres pg_isready -U codeweave

dev-down:
	docker compose down

clean:
	docker compose down -v
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .venv backend/.venv cli/.venv

# Phase 3: Celery worker / beat / Alembic migrations
worker:
	uv run --project backend celery -A codeweave.tasks worker -Q codeweave -l info

beat:
	uv run --project backend celery -A codeweave.tasks beat -l info

migrate:
	uv run --project backend alembic upgrade head

migrate-new:
	uv run --project backend alembic revision --autogenerate -m "$(m)"

migrate-down:
	uv run --project backend alembic downgrade -1