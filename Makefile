.PHONY: help install dev build test lint clean docker-up docker-down

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install all dependencies
	pnpm install
	uv sync

dev: ## Start development servers
	@echo "Starting API and Web dev servers..."
	@pnpm --filter @ai-video-editor/api dev &
	@pnpm --filter @ai-video-editor/web dev

build: ## Build all packages
	pnpm build
	uv run pytest --co -q

test: ## Run all tests
	uv run pytest tests/ -v

lint: ## Lint all code
	pnpm lint
	uv run ruff check services/
	uv run mypy services/

format: ## Format all code
	uv run black services/
	uv run ruff format services/

clean: ## Clean build artifacts
	rm -rf apps/*/dist apps/*/.next
	rm -rf services/*/__pycache__ services/*/*/__pycache__
	rm -rf .venv node_modules

docker-up: ## Start Docker Compose services
	docker-compose -f infra/docker/docker-compose.yml up --build -d

docker-down: ## Stop Docker Compose services
	docker-compose -f infra/docker/docker-compose.yml down

modal-deploy: ## Deploy Modal functions
	modal deploy infra/modal/ingest_modal.py
	modal deploy infra/modal/render_modal.py
	modal deploy infra/modal/upscale_modal.py

cli: ## Run CLI orchestrator
	uv run python services/orchestrator.py --reference $(REF) --song $(SONG) --clips $(CLIPS) --output $(OUT)
