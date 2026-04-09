#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="$ROOT_DIR/data/samples"
mkdir -p "$OUT_DIR"

URLS=(
  "https://user-images.githubusercontent.com/87690686/169808764-29e5678c-6762-4f43-8666-c3e60f94338f.mp4"
  "https://user-images.githubusercontent.com/87690686/137440639-fb08603d-9a35-474e-b65f-46b5c06b68d6.mp4"
  "https://user-images.githubusercontent.com/87690686/165095600-f68e0d42-830d-4c22-8940-c90c9f3bb817.mp4"
)

for url in "${URLS[@]}"; do
  name="$(basename "$url")"
  target="$OUT_DIR/$name"
  echo "Downloading $url"
  if command -v curl >/dev/null 2>&1; then
    curl -L --fail --retry 3 -o "$target" "$url"
  elif command -v wget >/dev/null 2>&1; then
    wget -O "$target" "$url"
  else
    echo "Neither curl nor wget is available" >&2
    exit 1
  fi
  echo "Saved: $target"
done

echo "Done. Videos are in $OUT_DIR"
