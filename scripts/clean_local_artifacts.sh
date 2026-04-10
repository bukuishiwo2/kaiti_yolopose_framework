#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

rm -rf "$ROOT_DIR/.idea"
rm -rf "$ROOT_DIR/.pytest_cache" "$ROOT_DIR/.mypy_cache" "$ROOT_DIR/.ruff_cache"
rm -rf "$ROOT_DIR/data/processed" "$ROOT_DIR/data/urfall" "$ROOT_DIR/data/Fall Detection Video Dataset"
find "$ROOT_DIR/data/samples" -maxdepth 1 -type f -name '*.mp4' -delete 2>/dev/null || true
rm -f "$ROOT_DIR"/*.pt
rm -f "$ROOT_DIR/models"/*.pt "$ROOT_DIR/models"/*.json
rm -rf "$ROOT_DIR/ros2_ws/build" "$ROOT_DIR/ros2_ws/install" "$ROOT_DIR/ros2_ws/log"
find "$ROOT_DIR" -type d -name '__pycache__' -prune -exec rm -rf {} +

mkdir -p "$ROOT_DIR/models" "$ROOT_DIR/outputs" "$ROOT_DIR/data/samples"
[ -f "$ROOT_DIR/models/.gitkeep" ] || touch "$ROOT_DIR/models/.gitkeep"
[ -f "$ROOT_DIR/outputs/.gitkeep" ] || touch "$ROOT_DIR/outputs/.gitkeep"
[ -f "$ROOT_DIR/data/samples/.gitkeep" ] || touch "$ROOT_DIR/data/samples/.gitkeep"

echo "Removed local-only artifacts under $ROOT_DIR"
