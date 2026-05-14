#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/Seb0g1/seb0g1.dev___loov.git"
APP_DIR="/home/seb0g1.dev___loov"

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
  if docker compose version >/dev/null 2>&1; then
    docker compose up -d --build
  elif command -v docker-compose >/dev/null 2>&1; then
    docker-compose up -d --build
  else
    echo "Docker is installed but compose is missing."
    exit 1
  fi
else
  echo "Docker is not installed."
  exit 1
fi
