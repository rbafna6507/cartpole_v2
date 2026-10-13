#!/usr/bin/env bash
# Read-only address discovery, then a local forward; no camera or motor access.
set -euo pipefail
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
exec python3 "$script_dir/vision_tunnel.py" "$@"
