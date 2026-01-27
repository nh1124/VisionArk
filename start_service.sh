#!/bin/bash

# AI TaskManagement OS - Docker Start Script for Linux

echo "========================================"
echo "AI TaskManagement OS - Docker Mode"
echo "========================================"
echo

echo "[1/3] Checking Docker installation..."
if ! command -v docker &> /dev/null; then
    echo "ERROR: Docker not found. Please install Docker."
    exit 1
fi

# Determine whether to use 'docker-compose' or 'docker compose'
if command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE="docker-compose"
elif docker compose version &> /dev/null; then
    DOCKER_COMPOSE="docker compose"
else
    echo "ERROR: docker-compose not found. Please install Docker Compose."
    exit 1
fi

echo "[2/3] Building containers (this may take a while on first run)..."
$DOCKER_COMPOSE --env-file .env -f infra/docker-compose.yml build --no-cache
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to build containers"
    exit 1
fi

echo "[3/3] Starting services..."
echo
echo "Services will be available at:"
echo "  - Frontend: http://localhost:3000"
echo "  - Backend:  http://localhost:8000"
echo "  - Database: localhost:5432"
echo
echo "Press Ctrl+C to stop all services"
echo

$DOCKER_COMPOSE --env-file .env -f infra/docker-compose.yml up
