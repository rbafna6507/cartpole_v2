# External policy executor requirements

A submitted SDK controller owns its acceleration decision in firmware `M_EXTERNAL`.
The native swing-up, approach, capture and balance laws do not run in this mode.
`validate_live_executor` therefore checks a learned actor's saved training snapshot
against the settings that still define its execution environment, while retaining
the complete snapshot as provenance. Admission reads settings; it never writes a
native gain, loads a profile, homes, centers, or changes the sensor reference.

## Native law settings

The learned-policy preflight allows differences in `leff`, `pw`, `pz`, `bal_pw`,
`pc1`, `pc2`, `ke`, `kpx`, `kdx`, `phase_soft`, `approach_v`, `catch_v`,
`approach_angle`, `catch_da`, `catch_a`, `catch_r`, and `giveup`. These configure
native feedback, pumping or capture, which `M_EXTERNAL` bypasses. In particular,
the firmware's native `leff` gain-model value is not a measurement of the actual
pendulum and changing it does not change the actor's training model.

## Shared motion and safety

External acceleration still passes through the firmware motion governor. Its
speed limit is `min(vmax, max(vmax_s, vmax_b))`; acceleration and braking use
`max(amax_s, amax_b)`; jerk uses `jmax`. Despite their names, the swing/balance
speed and acceleration settings are therefore relevant to external policies.
Their individual snapshot values remain pinned conservatively, even when a
particular change would leave the computed maximum unchanged.

Rail geometry, margins, the counted-home cap, switches, encoder health, stopped
admission, telemetry rate, fresh observation requirements, action TTL and session
leases remain enforced. Rail snapshot compatibility retains the existing 1 mm
half-length repeatability allowance plus binary32 serialization tolerance; the
live physical cap and host safety intersection remain strict. All parameter
fields outside the explicitly reviewed native-law set remain pinned (including
manual, spin/recovery and saved-return settings). This change does not claim
those other modes execute during an external run or relax their safety settings.
New/unknown parameter catalogs still fail admission.

## Observation source requirements

| Actor angle source | Angular rate source | Must match firmware `bw` |
| --- | --- | --- |
| `raw` | Filtered magnetic rate | Yes |
| `filtered` | Filtered magnetic rate | Yes |
| `fused` | Aligned filtered magnetic rate | Yes |
| `vision` | Camera rate | No |

The firmware estimator runs regardless of control mode. `bw` affects both its
filtered angle and magnetic angular rate. A raw-angle actor therefore still
requires the trained bandwidth. Vision-only actors consume neither estimator
output; they still require the normal healthy encoder/reference interlock and
explicit camera calibration, clock, freshness and frame binding. Fused actors
retain both the magnetic estimator requirement and their camera binding.

A mismatched required value fails before arming, naming that value. No automatic
per-run setting transaction is performed. For example, a filtered actor trained
at `bw=10` must still see `bw=10` even when its native feedback gains differ.
Operators must explicitly configure compatible sensor and shared motion settings
before retrying. The generic SDK action protocol itself does not require adopting
native feedback gains.

Preflight evidence records full live readback, required parameter names, ignored
native-law names, and any ignored observation parameter. The deployed
`policies/working.json` and `policies/1m.json` receive reviewed runtime/content pin
updates only. Their immutable training sources, weights, observation contracts,
action scales and parameter snapshots remain unchanged; the runtime migration
manifest and parity tests document this. These software checks do not establish
hardware acceptance.

Source basis: `firmware/teensy_executor/teensy_executor.ino` (`estimate`,
`serviceControl`, `M_EXTERNAL`), `firmware/teensy_executor/swing_controller.h`
(`recoverySpeedLimit`), `src/cartpole_sdk/policies/rig_observation.py`
(`rig_channels`), and `src/cartpole_sdk/rig/neural_runner.py`
(`validate_live_executor`).
