# Balance runner guard profiles

`scripts/run-balance-policy` defaults to `--guard-profile commissioning`. The
explicit `--guard-profile rig` option changes the runtime envelope and allows
`--duration` up to 60 seconds. The duration default remains 1 second in either
profile, and omitting `--execute` still runs stopped shadow inference.

| Runtime check | `commissioning` (default) | `rig` |
|---|---|---|
| Absolute counted position | Below the smaller of 0.12 m and actor `rail-rail_margin` | At most actor `rail-rail_fault_margin` |
| Absolute commanded velocity | Below 0.25 m/s | At most the smaller of actor `vmax+0.002` and 1.5 m/s |
| Absolute raw encoder angle | Below 0.15 rad | No host angle bound |
| Absolute observed angular rate | Below 1 rad/s | No host rate bound |
| Active rail braking | Refuse the next action | Continue subject to native authority |
| Maximum requested duration | 10 s | 60 s |

The rig rail/speed bounds use binary32 arithmetic and the same strict-exceedance
comparisons as the Teensy hard checks. Native rail braking, acceleration and jerk
governors, speed bounds, switches, faults, and command expiry remain active.
These are counted/commanded state bounds, not independent physical tracking or
stopping-distance guarantees.

Both profiles retain the balance-only actor's admission: centered and nearly
stationary upright, no rail braking, saved reference matching the explicit
expected count, healthy homed state with switches, exact live executor settings,
and matching actor/runtime hashes. Startup is rechecked after ARM before the
first action. Sensor source/freshness, 100 Hz cadence, observation-anchored
20 ms leases, and STOP on exit/failure remain unchanged. Choosing `rig` does not
turn a balance-only actor into a swing-up policy or admit a hanging start.

Acceleration authority is independently selected with `--max-acceleration`.
Its default remains 0.25 m/s²; it must be positive and no greater than 25 m/s².
Exceeding the requested ceiling refuses the action rather than clipping it.
The exception and `policy_failure` log name the exact raw demand, selected
`--max-acceleration`, and guard profile; the refused demand is never sent.
The executor retains its actual configured bounds. Selecting `rig` does not
increase acceleration authority automatically.

For an explicitly authorized balance experiment, add the profile and chosen
duration/ceiling to the existing command, for example
`--guard-profile rig --duration 30 --max-acceleration 3`. All existing actor,
reference, port, `--development-only` and explicit `--execute` arguments still
apply. A 3 m/s² ceiling can stop an actor whose declared output range reaches
25 m/s²; authorizing that complete range requires an explicit
`--max-acceleration 25`. This example is not a hardware acceptance claim.

The `balance_only_boundary` log records the selected profile, resolved limits
and comparisons, startup limits, requested/maximum duration, requested
acceleration ceiling, actor executor acceleration limit, and source hashes.
The returned result includes the profile, resolved runtime limits and requested
duration. Existing failure messages retain the crossed limit and actual value.

The CLI now supplies the existing `EncoderPublisher` to its `Rig` by default,
mirroring accepted encoder snapshots to UDP `127.0.0.1:3096` for the vision
viewer, as the console does. Use `--no-vision-telemetry` to disable this mirror.
This is read-only display telemetry; the actor still uses its pinned raw encoder
contract, and no camera measurements enter inference. `Rig` starts and closes
the publisher with the connection, including after a refusal. Direct callers
of `run_balance_policy` retain ownership of their existing `Rig` and publisher
lifecycle. Stopped shadow inference still reports demands above the execution
ceiling without arming.
