#!/bin/sh
# A loopback-only SSH tunnel over Tailscale. Keep this command running.
set -eu
host=${1:-rbafna@jetson}
port=${2:-3090}
case "$port" in *[!0-9]*|'') echo 'Port must be numeric' >&2; exit 2;; esac
printf 'Open http://127.0.0.1:%s in Chrome. Stop with Ctrl-C.\n' "$port"
exec ssh -N -T -o ExitOnForwardFailure=yes -o ServerAliveInterval=15 -o ServerAliveCountMax=3 \
  -L "127.0.0.1:$port:127.0.0.1:3090" "$host"
