#!/bin/bash
set -e

# Get absolute path to project root
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"

# Check if kitty is installed
if ! command -v kitty &> /dev/null; then
    echo "Error: kitty is not installed or not in PATH."
    echo "Please install kitty terminal or use 'npm run dev' manually."
    exit 1
fi

echo "Starting Session Siphon development session in kitty..."
kitty --session "${PROJECT_ROOT}/scripts/dev-session.conf" --directory "${PROJECT_ROOT}"
