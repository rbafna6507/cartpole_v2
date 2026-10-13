#!/bin/sh
set -eu
cd "$(dirname "$0")"
native_tmp="${TMPDIR:-/tmp}"
test_bin="$(mktemp "${native_tmp%/}/cartpole-native.XXXXXX")"
trap 'rm -f "$test_bin"' EXIT INT TERM
TMPDIR="$native_tmp" c++ -std=c++17 -Wall -Wextra -Werror -pedantic -fsanitize=address,undefined \
  -fno-omit-frame-pointer -g executor_test.cpp -o "$test_bin"
"$test_bin"
TMPDIR="$native_tmp" c++ -std=c++17 -Wall -Wextra -Werror -pedantic -fsanitize=address,undefined \
  -fno-omit-frame-pointer -g -I. hardware_test.cpp -o "$test_bin"
"$test_bin"
