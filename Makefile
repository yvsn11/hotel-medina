.DEFAULT_GOAL := help
.PHONY: help dev test test-backend test-frontend test-db migrate seed lint down clean

# Use backend/.venv when it exists, otherwise whatever is on PATH.
VENV_BIN := $(wildcard backend/.venv/bin)
ifneq ($(VENV_BIN),)
  RUN := cd backend && . .venv/bin/activate &&
else
  RUN := cd backend &&
endif

help: ## Show this help
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  %-14s %s\n", $$1, $$2}'

dev: ## Build and start db, api and web with Docker Compose
	docker compose up --build

test: test-backend test-frontend ## Run backend (pytest + coverage) and frontend tests

test-backend: ## Backend tests; needs TEST_DATABASE_URL (see `make test-db`)
	$(RUN) pytest --cov=app/services --cov-report=term-missing --cov-fail-under=85

test-frontend: ## Frontend tests
	cd frontend && npm test

test-db: ## Start the compose db and create the medina_test database
	docker compose up -d --wait db
	docker compose exec -T db psql -U medina -d medina -tc "SELECT 1 FROM pg_database WHERE datname='medina_test'" | grep -q 1 \
		|| docker compose exec -T db createdb -U medina medina_test

migrate: ## Apply database migrations to DATABASE_URL (host)
	$(RUN) flask --app wsgi db upgrade

seed: ## Load demo rooms, rates and accounts into DATABASE_URL (host)
	$(RUN) flask --app wsgi seed

lint: ## ruff check, ruff format --check, mypy, eslint
	$(RUN) ruff check . && ruff format --check . && mypy app
	cd frontend && npm run lint

down: ## Stop containers (keeps the database volume)
	docker compose down

clean: ## Stop containers and delete the database volume and build output
	docker compose down -v --remove-orphans
	rm -rf frontend/dist backend/.pytest_cache backend/.mypy_cache backend/.ruff_cache backend/.coverage backend/coverage.xml backend/htmlcov
