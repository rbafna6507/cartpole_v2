#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "$0")/.." && pwd)"
dependency_dir="$(mktemp -d "${TMPDIR:-/tmp}/cartpole-libraries.XXXXXX")"
trap 'rm -rf -- "$dependency_dir"' EXIT
unzip -q "$repo_root/third_party/FastAccelStepper-1.2.8.zip" -d "$dependency_dir"
arduino-cli compile --fqbn esp32:esp32:esp32 --libraries "$dependency_dir" \
  --build-path "${TMPDIR:-/tmp}/cartpole-cart-sine-build" "$repo_root/cart_sine"
arduino-cli compile --fqbn esp32:esp32:esp32 \
  --build-path "${TMPDIR:-/tmp}/cartpole-cart-simple-build" "$repo_root/cart_simple"
