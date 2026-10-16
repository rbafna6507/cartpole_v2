# Cartpole v2 checkpoint — 2026-10-16

This is the current task status after native tuning and the console-default work.
Earlier paused-development notes are historical. This checkpoint makes no new
hardware-control, sensor-calibration, or physical-identification acceptance claim.

| Area | Implemented and demonstrated | Remaining |
| --- | --- | --- |
| Native control | Teensy 1 kHz encoder-only AUTO; tuned bw10 profile preserved and loaded by the console; bw8 smoothing candidate saved separately; repeated 25 s tests and 60 s holds with return | Longer/more diverse stability and catch repeatability tests; reference 330 remains an experimental trim |
| System identification | Timestamp/reference-aware Rig log adapter; effective length, damping, commanded-input gain and delay fitting; independent held-out assessment; raw evidence and rejection diagnostics | No accepted physical model; assess new runs and gather independent excitation/cart motion measurements; separate sensor/timing bias from dynamics |
| Python AUTO/BAL | Local experimental SDK commands at 100/250 Hz; live-parameter mapping; MCU external acceleration leases and governor; protocol tests and MuJoCo integration checks | Not deployed or physically validated; native capture/approach/recovery state machines are not fully reproduced; complete parity or document intentional differences, then short guarded trials |
| Vision encoding | Maintained runtime separate from archive/vision3; SDK vision observations; encoder mirroring from sole serial owner; dashboard traces and dense stream | Current-reference angular alignment and dynamic accuracy/latency validation |
| Fused angle | SDK complementary angle-bias observer with explicit clocks, history, validity and source identities; replayable shadow logging and dashboard | Shadow only, not control eligible; no fused rate; no commissioned vision-only/fused AUTO/BAL path |

## Identification detail

The last preserved physical fits used earlier native g1 data for training and
separate h1/k1 recordings for assessment. Candidate effective length was about
0.152 m, but both reports were rejected: training integral NRMSE 0.189 exceeds 0.15,
input-zero diagnostic was −8.83 degrees, and held-out half-second prediction RMS
was 0.879–0.895 rad versus the 0.08-rad gate. Those estimates were not copied into
MuJoCo. Predictions include causal rate-initialization uncertainty; do not
attribute all error to plant dynamics. Commanded acceleration and step count do
not independently identify motor tracking, mass, force gain or slip.

The new successful native runs provide additional data, but have not yet yielded
an accepted ID model. Balance feedback correlates input with state; successful
control alone does not establish sufficiently independent excitation. The
simulator and RL infrastructure work, but the physical plant remains provisional.

## Python control detail

Four earlier one-seed, ten-second MuJoCo checks completed without faults: AUTO
held 7.87 s / 8.10 s at 100/250 Hz; BAL held 10 s at both rates. These are software checks
with ideal sensing and a provisional plant, not rig performance. The SDK maps
energy/feedback terms from controller parameters and sends raw demanded
acceleration. The Teensy retains its 1 kHz governor, switch handling and expiring
leases. Native AUTO/BAL continue to execute on the Teensy. Local Python commands
currently stop on completion; rehome is explicit.

The current root console's startup profile covers Python commands as well as
native AUTO/BAL. It loads the preserved default unless --keep-board-params or an
explicit --startup-profile is selected, then the Python runner reads live settings.
The deployed snapshot contains native console commands only. Copying the entire
local source onto that release would therefore be a separate deployment change.

## Vision/fusion detail

The last measured dense-stream run had approximately 75 FPS acquisition,38–39 FPS
tracking and 40 FPS preview. These are measured historical rates, not a fresh
service-health check or guaranteed control cadence. Fusion slowly corrects
magnetic angle bias using time-aligned camera history. It does not fuse rates or
repair arbitrary nonlinear/history-dependent encoder error. Current policy
entry points select magnetic/step sources; using vision/fusion for actuation
still needs an explicit observation/control bridge and commissioning.

The practical order is encoder-based Python BAL bring-up, Python AUTO validation,
then calibrated vision/fusion shadow comparison and bounded feedback trials.
System-ID analysis and experiment design can proceed alongside the Python work.

## Version-control scope

The previous HEAD was ff34f5a (2026-10-14, cart switches and stopped calibration).
This checkpoint includes subsequent source, firmware, profiles, documentation,
tests and curated evidence, plus exact deployed release snapshots in releases/.
The captured deployment includes seven named release directories, the legacy
current directory, and the legacy standalone firmware artifact. Snapshot hashes
record files as found on 2026-10-16; old embedded manifests can predate later
in-place patches. The new snapshot manifest is authoritative for this capture.

Virtual environments, caches, generated runs/log directories, and the old
archive/uncommitted-evidence backup remain outside Git. Curated evidence and raw
recording manifests are committed; full Jetson run directories remain on the
Jetson. No deployment, flash, calibration or motor command was issued for this
checkpoint. The owner will push the branch.

Verification: full local suite: 721 passed, 7 skipped, 384 subtests; vision frontend
19 Node tests passed. Release bytes, file counts and executable flags are checked
against the captured manifest. See evidence/checkpoint-20261016/ and releases/.
