COMPOSE = docker compose --env-file .env -f infra/docker-compose.yml
COMPOSE_DEV = $(COMPOSE) -f infra/docker-compose.dev.yml
COMPOSE_PROD = $(COMPOSE) -f infra/docker-compose.prod.yml

.PHONY: up down logs ps db api web test lint migrate migration deploy backup password-hash vapid-keys mcp

up:            ## Build and start everything in Docker (locally, Postgres stays reachable on localhost)
	$(COMPOSE_DEV) up -d --build

down:          ## Stop everything
	$(COMPOSE) down

logs:          ## Follow logs of all containers
	$(COMPOSE) logs -f

ps:
	$(COMPOSE) ps

db:            ## Start Postgres only, exposed on localhost (for local development)
	$(COMPOSE_DEV) up -d --wait db

api: db        ## Run the API locally with reload (port 8000)
	cd backend && uv run alembic upgrade head && uv run uvicorn app.main:app --reload

mcp: db        ## Run the MCP server locally with reload (port 8001)
	cd backend && MCP_PUBLIC_URL=http://localhost:8001 uv run uvicorn app.mcp.app:app --port 8001 --reload

web:           ## Run the frontend locally with Vite (port 5173, proxies /api to 8000)
	cd frontend && pnpm dev

test: db       ## Backend tests against the local database
	cd backend && uv run pytest

lint:
	cd backend && uv run ruff check . && uv run ruff format --check .
	cd frontend && pnpm lint

migrate: db
	cd backend && uv run alembic upgrade head

migration: db  ## New migration: make migration m="description"
	cd backend && uv run alembic revision --autogenerate -m "$(m)"

deploy:        ## Server: pull the CI images and restart (no local build)
	git pull --ff-only
	$(COMPOSE_PROD) pull
	$(COMPOSE_PROD) up -d --no-build --remove-orphans
	docker image prune -f

backup:        ## Server: write a database dump now
	infra/backup/pg-backup.sh

password-hash: ## Create the bcrypt hash for COMPASS_BASIC_AUTH_HASH (escaped for .env)
	@printf "Password: "; stty -echo; read -r pw; stty echo; echo; \
	[ -n "$$pw" ] || { echo "Empty password" >&2; exit 1; }; \
	docker run --rm caddy:2.10-alpine caddy hash-password --plaintext "$$pw" | sed 's/\$$/$$$$/g'

vapid-keys:    ## Create the VAPID key pair for web push (lines for .env)
	cd backend && uv run python -m app.services.push
