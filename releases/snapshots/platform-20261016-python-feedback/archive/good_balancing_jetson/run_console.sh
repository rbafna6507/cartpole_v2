#!/usr/bin/env bash
set -euo pipefail
bundle_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec uv run --project "$bundle_dir" cartpole-console "$@"
