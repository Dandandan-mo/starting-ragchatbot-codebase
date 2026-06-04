#!/usr/bin/env bash
set -euo pipefail

FRONTEND_DIR="$(cd "$(dirname "$0")/.." && pwd)/frontend"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== Frontend Quality Checks ==="

# Ensure prettier is installed
if ! command -v npx &> /dev/null; then
    echo "ERROR: npx not found. Install Node.js to run frontend quality checks."
    exit 1
fi

cd "$ROOT_DIR"

if [ ! -d node_modules ]; then
    echo "Installing dependencies..."
    npm install --silent
fi

echo ""
echo "Checking formatting with Prettier..."
npx prettier --check "$FRONTEND_DIR/**/*.{js,css,html}"

echo ""
echo "All frontend quality checks passed."
