.PHONY: ingest ingest-cached ingest-parse-only dev test lint build check up down logs docker-ingest

# ── Ingestion ─────────────────────────────────────────────────────────────────

# Télécharge le dump, parse et peuple la DB (pipeline complet)
ingest:
	python scripts/check_ingest.py --data-dir ./data

# Même chose sans re-télécharger si un XML est déjà présent
ingest-cached:
	python scripts/check_ingest.py --data-dir ./data --no-download

# Parse seulement (sans toucher à la DB) — debug/validation du parser
ingest-parse-only:
	python scripts/check_ingest.py --data-dir ./data --no-download --no-db

# ── Développement ─────────────────────────────────────────────────────────────

# Serveur de développement local
dev:
	uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# Tests unitaires
test:
	pytest tests/ -v

# Lint + type check
lint:
	ruff check src/ tests/ scripts/
	mypy src/ --ignore-missing-imports

# Lint + test
check: lint test

# ── Docker ────────────────────────────────────────────────────────────────────

# Build l'image Docker
build:
	docker compose build

# Démarrage en arrière-plan
up:
	docker compose up -d

# Arrêt des conteneurs
down:
	docker compose down

# Logs en direct
logs:
	docker compose logs -f app

# Ingestion manuelle dans le conteneur Docker
docker-ingest:
	docker compose exec app python scripts/check_ingest.py --data-dir /app/data
