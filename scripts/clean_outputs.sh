#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

rm -rf "$ROOT_DIR/outputs/vis"
rm -f "$ROOT_DIR/outputs/pose_events.jsonl"
rm -rf "$ROOT_DIR/outputs/eval_test"
rm -rf "$ROOT_DIR/outputs/tune_smoke"
rm -rf "$ROOT_DIR/outputs/eval_urfall" "$ROOT_DIR/outputs/eval_urfall_track" "$ROOT_DIR/outputs/eval_urfall_sequence" "$ROOT_DIR/outputs/eval_urfall_sequence_fallvision"
rm -rf "$ROOT_DIR/outputs/tune_fall_grid" "$ROOT_DIR/outputs/tune_fall_grid_predict" "$ROOT_DIR/outputs/tune_fall_grid_sequence" "$ROOT_DIR/outputs/tune_fall_grid_sequence_refine"
rm -f "$ROOT_DIR/outputs/eval_compare_predict_vs_track.csv"
find "$ROOT_DIR" -type d -name '__pycache__' -prune -exec rm -rf {} +

mkdir -p "$ROOT_DIR/outputs" "$ROOT_DIR/models"
[ -f "$ROOT_DIR/outputs/.gitkeep" ] || touch "$ROOT_DIR/outputs/.gitkeep"
[ -f "$ROOT_DIR/models/.gitkeep" ] || touch "$ROOT_DIR/models/.gitkeep"

echo "Cleaned runtime outputs under $ROOT_DIR"
