# Test commands. External AI providers are mocked; nothing here calls a paid LLM API.
#
#   make test                  backend, frontend, and end-to-end
#   make test-backend-lint     Ruff
#   make test-backend          all Pytest modules
#   make test-backend-api      HTTP client tests
#   make test-backend-service  service and provider tests
#   make test-backend-agent    agent tests
#   make test-backend-tool     tool tests
#   make test-backend-db       PostgreSQL tests (skips when the test database is down)
#   make test-frontend         Vitest and React Testing Library
#   make test-e2e              Playwright critical chat flow

.PHONY: test test-backend-lint test-backend test-backend-api test-backend-service test-backend-agent test-backend-tool test-backend-db test-frontend test-e2e

test: test-backend test-frontend test-e2e

test-backend-lint:
	cd backend && .venv/bin/ruff check app tests migrations

test-backend:
	cd backend && .venv/bin/pytest

test-backend-api:
	cd backend && .venv/bin/pytest -m api

test-backend-service:
	cd backend && .venv/bin/pytest -m service

test-backend-agent:
	cd backend && .venv/bin/pytest -m agent

test-backend-tool:
	cd backend && .venv/bin/pytest -m tool

test-backend-db:
	cd backend && .venv/bin/pytest -m db

test-frontend:
	cd frontend && npm test

test-e2e:
	cd frontend && npm run test:e2e
