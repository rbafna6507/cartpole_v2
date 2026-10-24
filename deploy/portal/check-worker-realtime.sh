#!/bin/bash
# Target-specific offline validation. No serial access or hardware worker start.
# Run on Jetson with physical console experiments idle; sudo may ask for a password.
set -euo pipefail

exec sudo systemd-run --wait --pipe --collect --uid=rbafna \
  --property=WorkingDirectory=/home/rbafna/cartpole-portal/source \
  --property=LimitRTPRIO=10 --property=CPUSchedulingPolicy=rr \
  --property=CPUSchedulingPriority=10 --property=CPUAffinity=4 \
  --property=NoNewPrivileges=yes --property=RuntimeMaxSec=45 \
  --setenv=CARTPOLE_TEST_REALTIME_CPU=5 \
  --setenv=PYTHONPATH=/home/rbafna/cartpole-portal/source/src \
  --setenv=PYTHONDONTWRITEBYTECODE=1 \
  /bin/sh -ec '
    /home/rbafna/cartpole_v2/.venv/bin/python -m pytest -p no:cacheprovider -q tests/test_portal_realtime_linux.py
    exec .venv/bin/python deploy/portal/check-actor-startup.py \
      --cpu 5 \
      --numpy-root /home/rbafna/cartpole-portal/sandbox-packages \
      --artifact /home/rbafna/.local/state/cartpole-portal/store/artifacts/0d17c63c7b779286ab9954da8bc7cc74850f7da235fc393f35867115819dbe16.py \
      --telemetry /home/rbafna/.local/state/cartpole-portal/hardware-recordings/6b248056287743209fce0a5b3a98fe7f-044bd9ac4b7548448411fb7c474e24d2/telemetry.jsonl
  '
