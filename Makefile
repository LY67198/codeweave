# CodeWeave Makefile
# Wraps uv commands with correct flags for workspace (uv 0.11.x quirk on Windows)

.PHONY: sync install test test-backend test-integration lint format clean dev-up dev-down

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