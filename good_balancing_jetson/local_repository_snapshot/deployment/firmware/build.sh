#!/bin/sh
set -eu
firmware_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
build_tmp="${TMPDIR:-/tmp}"
build_root="$(mktemp -d "${build_tmp%/}/cartpole-teensy.XXXXXX")"
TMPDIR="$build_tmp" arduino-cli compile --fqbn teensy:avr:teensy41 \
  --build-path "$build_root/build" --output-dir "$build_root/output" \
  "$firmware_dir/deployment_executor"
printf 'Build artifacts: %s/output\n' "$build_root"
