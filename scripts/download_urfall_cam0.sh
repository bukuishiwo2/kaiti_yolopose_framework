#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE_URL="https://fenix.ur.edu.pl/~mkepski/ds/data"
OUT_VIDEO_DIR="$ROOT_DIR/data/urfall/cam0_mp4"
OUT_LABEL_DIR="$ROOT_DIR/data/urfall/labels_raw"
MODE="all"  # all | falls | adls

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      MODE="$2"
      shift 2
      ;;
    *)
      echo "Unknown arg: $1" >&2
      exit 1
      ;;
  esac
done

mkdir -p "$OUT_VIDEO_DIR" "$OUT_LABEL_DIR"

download() {
  local url="$1"
  local target="$2"
  if command -v curl >/dev/null 2>&1; then
    curl -L --fail --retry 3 -o "$target" "$url"
  elif command -v wget >/dev/null 2>&1; then
    wget -O "$target" "$url"
  else
    echo "Neither curl nor wget is available" >&2
    exit 1
  fi
}

if [[ "$MODE" == "all" || "$MODE" == "falls" ]]; then
  for i in $(seq -w 1 30); do
    f="fall-${i}-cam0.mp4"
    echo "Downloading $f"
    download "$BASE_URL/$f" "$OUT_VIDEO_DIR/$f"
  done
fi

if [[ "$MODE" == "all" || "$MODE" == "adls" ]]; then
  for i in $(seq -w 1 40); do
    f="adl-${i}-cam0.mp4"
    echo "Downloading $f"
    download "$BASE_URL/$f" "$OUT_VIDEO_DIR/$f"
  done
fi

# Feature-label files provided by dataset page (used to auto-build fall segments)
for f in urfall-cam0-falls.csv urfall-cam0-adls.csv; do
  echo "Downloading $f"
  download "$BASE_URL/$f" "$OUT_LABEL_DIR/$f"
done

echo "Done. Videos: $OUT_VIDEO_DIR"
echo "Done. Raw labels: $OUT_LABEL_DIR"
