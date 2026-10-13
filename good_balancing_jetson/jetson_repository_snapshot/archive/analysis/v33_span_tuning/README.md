# Supervised swing-up tuning: rail span and capture time

## Result

After the user restored motor power, eight powered trials completed without
serial or firmware faults. The earlier no-response fault (052) was caused by an
unpowered motor and is excluded from gain comparisons.

| Candidate | Observed swing-up bounds | Time to hold | Evidence |
|---|---|---|---|
| Full-span reference | about −135 to +135 mm | 4.53, 13.85, 31.55 s | Three 30-second holds |
| 240 mm envelope, `ke=3` | −119.85 to +119.59 mm | 14.20 s | One 10-second hold; powered repeat failed |
| 255 mm envelope, `ke=3` | −127.28 to +127.24 mm | 13.29 s | One 10-second hold; powered repeat failed |

**Keep the full-span reference as the demonstrated repeatable candidate.**
The smaller envelopes have not established a repeatable improvement. This batch
does not prove a fundamental minimum rail length or a globally optimal gain set.
The 255 mm/`ke=4` run caught near 72 s, but its deadline ended that hold after 2.805 s;
it was not an observed loss of balance. Deliberate user disturbances are annotated.

[Complete comparison](span_comparison.md) · [Plot](span_comparison.png) · [Batch results](batch_results.json)

## Reference settings

Use [recommended_commands.txt](recommended_commands.txt) or
[recommended_settings.json](recommended_settings.json). The preset uses
`ke=4`, `kpx=40`, `kdx=2`, `pw=6`, `pz=0.85`, `pc1=-3`, `pc2=-4`, `bw=30`, `catch_a=0.25`,
`catch_r=2`, `catch_da=2`, `approach_angle=0.8`, `approach_v=0.3`, `catch_v=0.3`,
`phase_soft=2`, `giveup=0.8`, `rail=0.15`.

Applied ceilings remain `spin_trip_rad_s=150`, jmax 150, `amax_s=25`, `amax_b=25`,
and `vmax=1.5`, `vmax_s=1.5`, `vmax_b=1.5`. Only the jerk increase to 150 was newly authorized;
the other ceilings were preserved. Bandwidth is tunable.

The command files stop/configure/print parameters and do not start motion or
change the encoder reference. Runtime presets do not replace boot defaults.
Firmware v33 permits jmax 150 but still boots at 100. Direct upright target 3528
persists. Establish the physical center before motion; `home` sets the current
position as zero and does not seek center.

## Smaller software envelopes

The physical rail is still 300 mm. For experimental compact trials, `rail=0.135`
means normal braking at ±120 mm and fault stop at ±125 mm; `rail=0.1425` means normal
braking at ±127.5 mm and fault stop at ±132.5 mm. The runner only permits shrinking
inside the physical ±150 mm rail and applies changes at a stopped inferred center.
The compact/intermediate candidate files are experimental, not replacements for
the repeated full-span reference. Position/span are inferred from step pulses.

## Final hardware state

Request 064 returned the cart to inferred x=+1.39 mm. IDLE, zero commanded speed
and acceleration, and ENABLE GPIO27 HIGH (drivers disabled) were verified.
Request 065 closed the serial session; no motion is queued and the port is free.

The earlier serial fault in 048 remains unexplained; subsequent powered trials
completed cleanly. Its malformed frame was not retained by the old parser;
future malformed frames are now logged without weakening stop-on-error checks.
Firmware compile/flash and setter checks passed; the runner/scoring checks also
passed. Full settings, telemetry, and command logs are retained at:
`/Users/sajivshah/Documents/InvertedPendulum/autonomous_tuning/20260918_resume/`.
