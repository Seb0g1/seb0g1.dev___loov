#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/Seb0g1/seb0g1.dev___loov.git"
APP_DIR="/home/seb0g1.dev___loov"
PROJECT_NAME="seb0g1loov"

compose() {
  if docker compose version >/dev/null 2>&1; then
    COMPOSE_PROJECT_NAME="$PROJECT_NAME" docker compose "$@"
  elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_PROJECT_NAME="$PROJECT_NAME" docker-compose "$@"
  else
    echo "Docker compose is not available."
    exit 1
  fi
}

if [ ! -d "/home" ]; then
  echo "/home not found"
  exit 1
fi

mkdir -p "$APP_DIR"
cd "$APP_DIR"

if [ ! -d ".git" ]; then
  git clone "$REPO_URL" .
fi

if [ ! -f ".env" ] && [ -f ".env.example" ]; then
  cp .env.example .env
  echo "Created .env from .env.example. Edit it now."
fi

if command -v docker >/dev/null 2>&1; then
  compose up -d db
  until compose exec -T db pg_isready -U tehno -d tehno_halava >/dev/null 2>&1; do
    sleep 2
  done
  compose rm -sf backend bot frontend || true
  compose up -d --build backend bot frontend
else
  echo "Docker is not installed."
  exit 1
fi

