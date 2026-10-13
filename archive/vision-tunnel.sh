#!/usr/bin/env bash
# Local viewing only; no remote command, camera startup, or motor access.
set -euo pipefail
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [[ ${1:-} == --help || ${1:-} == -h ]]; then
  printf 'Usage: %s [user@host]\nEnvironment: JETSON_SSH_TARGET, JETSON_KNOWN_HOSTS, LOCAL_PORT (3095), REMOTE_PORT (3090).\n' "$0"
  exit 0
fi
if (( $# > 1 )); then printf 'Expected at most one SSH destination.\n' >&2; exit 2; fi
target=${1:-${JETSON_SSH_TARGET:-rbafna@2601:408:c402:c85f:acc2:faf9:770:a44}}
local_port=${LOCAL_PORT:-3095}
remote_port=${REMOTE_PORT:-3090}
known_hosts=${JETSON_KNOWN_HOSTS:-$script_dir/jetson_known_hosts}
for port in "$local_port" "$remote_port"; do
  if [[ ! $port =~ ^[0-9]{1,5}$ ]] || (( 10#$port < 1 || 10#$port > 65535 )); then
    printf 'Ports must be integers from 1 to 65535.\n' >&2; exit 2
  fi
done
if [[ -z $target || $target == -* || $target =~ [[:space:]] ]]; then
  printf 'Invalid SSH destination.\n' >&2; exit 2
fi
if [[ ! -r $known_hosts ]]; then
  printf 'Verified host-key file is missing: %s\nSet JETSON_KNOWN_HOSTS to your verified known_hosts file.\n' "$known_hosts" >&2
  exit 2
fi
printf 'Opening tunnel to %s. After SSH connects, open http://127.0.0.1:%s/\nKeep this terminal open; Ctrl-C closes the tunnel.\n' "$target" "$local_port"
# OpenSSH parses this option again; quote for its config syntax as well as Bash.
known_hosts_escaped=${known_hosts//\\/\\\\}
known_hosts_escaped=${known_hosts_escaped//\"/\\\"}
exec ssh -N -T -o ControlMaster=no -o ControlPath=none \
  -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
  -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=\"$known_hosts_escaped\"" \
  -L "127.0.0.1:$local_port:127.0.0.1:$remote_port" "$target"
