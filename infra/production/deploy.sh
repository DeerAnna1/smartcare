#!/bin/sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/docker-compose.prod.yml"
ENV_FILE="${SCRIPT_DIR}/.env.production"

if [ ! -f "${ENV_FILE}" ]; then
    echo "Missing ${ENV_FILE}. Copy .env.production.example and fill in production values." >&2
    exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "Docker is not installed." >&2
    exit 1
fi

mkdir -p "${SCRIPT_DIR}/backups"

docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" config --quiet

# Build sequentially to avoid exhausting memory on a 4 GB server.
docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" build api
docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" build web
docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" pull postgres redis caddy backup
docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" up -d
docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" ps

echo "Deployment started at SITE_ADDRESS. HTTPS is automatic when SITE_ADDRESS uses a valid public domain."
