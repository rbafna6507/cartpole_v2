#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "$0")/.." && pwd)"
test_dir="$(mktemp -d "${TMPDIR:-/tmp}/cartpole-sine-tests.XXXXXX")"
trap 'rm -rf -- "$test_dir"' EXIT
"${CXX:-clang++}" -std=c++11 -O2 -Wall -Wextra -Werror \
  "$repo_root/tests/sine_motion_test.cpp" -o "$test_dir/sine_motion_test"
"$test_dir/sine_motion_test"
"${CXX:-clang++}" -std=c++17 -O2 -Wall -Wextra -Werror \
  -I"$repo_root/tests/sine_fakes" \
  "$repo_root/tests/sine_console_test.cpp" -o "$test_dir/sine_console_test"
"$test_dir/sine_console_test"
