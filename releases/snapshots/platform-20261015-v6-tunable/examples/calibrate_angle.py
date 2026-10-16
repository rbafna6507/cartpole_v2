#!/usr/bin/env python3
"""Offline calibration tools; never opens a rig, port, camera, or network connection.

Run from an installed cartpole-sdk environment::

    python examples/calibrate_angle.py fit paired-windows.json --output profile.json
    python examples/calibrate_angle.py report profile.json
    python examples/calibrate_angle.py approve profile.json --output approved.json \
        --approved-by operator --approved-at 2026-10-15T16:00:00Z
    python examples/calibrate_angle.py check approved.json \
        --hardware-id YOUR_RIG --source-id as5600-raw-12bit \
        --fixture-id YOUR_FIXTURE --sensor-config-id YOUR_SENSOR_CONFIGURATION

The complete input/output contract and acquisition procedure are documented in
 evidence/phase3/retuning-20261015/calibration/README.md. Approval records an
operator's explicit decision after validation; it is never supplied by fitting.
"""
from cartpole_sdk.sensing.calibration import main

if __name__ == '__main__':
    raise SystemExit(main())
