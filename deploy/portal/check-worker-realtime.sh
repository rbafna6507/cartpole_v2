#!/bin/bash
# Target-specific offline validation. No serial access or hardware worker start.
# Run on Jetson with physical console experiments idle; sudo may ask for a password.
set -euo pipefail

# systemd 249 rejects RR/priority transient properties on this host.
# Grant only the allowance here; chrt selects RR10 after switching to rbafna.
exec sudo systemd-run --wait --pipe --collect --uid=rbafna \
  --property=WorkingDirectory=/home/rbafna/cartpole-portal/source \
  --property=LimitRTPRIO=10 --property=CPUAffinity=4 \
  --property=NoNewPrivileges=yes --property=RuntimeMaxSec=45 \
  --setenv=CARTPOLE_TEST_REALTIME_CPU=5 \
  --setenv=PYTHONPATH=/home/rbafna/cartpole-portal/source/src \
  --setenv=PYTHONDONTWRITEBYTECODE=1 \
  /usr/bin/chrt --rr 10 /bin/sh -ec '
    /home/rbafna/cartpole_v2/.venv/bin/python -m pytest -p no:cacheprovider -q tests/test_portal_realtime_linux.py
    exec .venv/bin/python deploy/portal/check-actor-startup.py \
      --cpu 5 \
      --numpy-root /home/rbafna/cartpole-portal/sandbox-packages \
      --artifact /home/rbafna/cartpole-portal/source/policies/working.json \
      --telemetry /home/rbafna/.local/state/cartpole-portal/hardware-recordings/6b248056287743209fce0a5b3a98fe7f-044bd9ac4b7548448411fb7c474e24d2/telemetry.jsonl
  '
