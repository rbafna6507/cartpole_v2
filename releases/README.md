# Preserved Jetson releases

These are exact file snapshots captured on 2026-10-16 from
`/home/rbafna/cartpole-v2-live`. The active operator release at capture was
`platform-20261015-v6-tunable`, including the new default-profile console and
both bandwidth 10 and bandwidth 8 tuning profiles. They are preserved separately
from the newer development source at the repository root.

| Snapshot | Purpose / retained firmware image |
| --- | --- |
| platform-20261013 | Initial platform release; firmware source retained |
| platform-20261014-cart-switches | Cart-only switch fix; executor-v2-cart2.hex |
| platform-20261014-encoder | Encoder health/configuration diagnostics; executor-v3-encguard.hex |
| platform-20261014-parameters | Parameter controls and 750 mm homing; executor-v3-params-home750.hex |
| platform-20261015-rehome | Saved-center return; executor-v4-rehome.hex |
| platform-20261015-v5-jerk600 | Calibration-model support and higher jerk ceiling; executor-v5-calmodel-jerk600.hex plus recovery image |
| platform-20261015-v6-tunable | Measured rail/motion tunables; executor-v6-measuredrail-tunable.hex plus recovery image |
| legacy-current | Earlier directory named current; it was a separate directory, not a pointer to the active release |
| legacy-firmware | Standalone firmware image found in the top-level firmware directory; retained as a historical artifact, not identified as the active board image |

`manifest-20261016.json` records original paths, capture time, SHA256, sizes and
executable bits. Old manifests inside snapshots are retained byte-for-byte and
may predate in-place updates. The new manifest describes actual captured files.
No old snapshot is rewritten to match today's SDK. In particular, the v6 native
console snapshot does not contain the newer experimental Python AUTO/BAL commands
present in the repository root.

A snapshot can be copied to a fresh Jetson directory and its own pyproject.toml
and uv.lock used to reconstruct dependencies. For the current operator version:

```sh
cd releases/snapshots/platform-20261015-v6-tunable
uv run --locked --extra hardware cartpole-console \
  --port /dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00 --rate 250
```

This is an operator console connection, not an automatic motion or flash command.
Read the rig usage and firmware instructions before restoring old software; old
releases differ in protocol, safety behavior and calibration support. Firmware
upload on this PCB still requires motor power OFF because enable can float in
bootloader mode. Calibration and home are live hardware state, not restored by
copying source or loading a gain profile.

The capture excludes virtual environments, caches, build/dist directories,
generated runs/logs/reports, egg metadata and macOS resource-fork files. All
nonexcluded files, including source, lockfiles, profiles, tests, documentation,
firmware artifacts and release verification evidence, are included. Raw run
directories remain on the Jetson; curated evidence lives in the root evidence/.

## New experimental Python release

`platform-20261016-python-feedback` is a new SDK snapshot, separate from the
historical Jetson captures above. Its own `release-manifest.json` records the
packaged files. Native AUTO/BAL and the working bw10 startup profile remain;
`python-auto`/`python-bal` use the experimental host feedback controller with
existing executor-v6-measuredrail firmware. No flash is required.

One 25-second Python AUTO trial held for 21.8 seconds after capture; a repeat
hit the right switch, and another trial stopped on host cadence. Full physical
home subsequently succeeded. This release is for explicit commissioning, not a
claim of repeatable production readiness. Standalone physical Python BAL remains
pending. See its RELEASE.md and the root Python-control evidence for details.
