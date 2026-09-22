UV := uv
MANAGE := $(UV) run python manage.py
PORT ?= 8000

.PHONY: install sync docker-build docker-up docker-down docker-dev \
	docker-dev-down db-up db-down db-logs run-dev run-prod migrations migrate \
	superuser seed-demo schema shell check test

install sync:
	$(UV) sync

docker-build:
	docker compose build app

docker-up:
	docker compose up --build -d

docker-down:
	docker compose down

docker-dev:
	docker compose -f docker-compose.dev.yml up --build

docker-dev-down:
	docker compose -f docker-compose.dev.yml down

db-up:
	docker compose -f docker-compose.dev.yml up -d db

db-down:
	docker compose -f docker-compose.dev.yml stop db

db-logs:
	docker compose -f docker-compose.dev.yml logs -f db

run-dev:
	$(MANAGE) runserver 0.0.0.0:$(PORT)

run-prod:
	DJANGO_SETTINGS_MODULE=config.settings.prod \
	$(UV) run gunicorn config.wsgi:application --bind 0.0.0.0:$(PORT)

migrations:
	$(MANAGE) makemigrations

migrate:
	$(MANAGE) migrate

superuser:
	$(MANAGE) createsuperuser

seed-demo:
	$(MANAGE) seed_demo

schema:
	$(MANAGE) spectacular --validate --fail-on-warn --file docs/openapi.yml

shell:
	$(MANAGE) shell

check:
	$(MANAGE) check
	$(UV) run ruff check .
	$(UV) run ruff format --check .
	$(UV) run mypy .

test:
	$(MANAGE) test
