# Characterize the installed rig before training

Use `cartpole-deploy` from an activated installation; simulation is the default.
Pass global options such as `--backend hardware` before the subcommand. This
workflow collects raw encoder samples and device timestamps, fits passive
pendulum dynamics, and records bounded drive experiments through the same SDK.

## Establish the physical configuration

Record the installed arm length, arm and tip masses, actual assembled COM, rail
travel, pulley pitch/teeth and microstep setting. Measure the travel available to
the carriage reference point, not merely the extrusion length. Save a copy of
`configs/rig-125mm.json` with your measured values and provenance. Do not change
the firmware's ceilings based on a simulation result alone.

The default 125 mm profile uses a historical fit. A free-release period identifies
`L_eff = I_pivot / (mass * COM)`, not physical arm length. Mass and COM must be
measured independently; `I_pivot = mass * COM * L_eff` then gives inertia for
MuJoCo. Replacing the arm or adding weights requires a new profile and dataset.

Before enabling hardware: inspect the firmware pinout/shared enable, verify
encoder magnet status and zero/sign with drivers disabled, establish a physical
stop/inhibit, check actual travel, and secure the Z assembly. The MCU has no
independent carriage position sensor or implemented limit-switch inputs.

## 1. Stationary sensor capture

Physically hold the pendulum and cart stationary with drivers disabled. Use a new
directory name for every run:

```sh
cartpole-deploy --backend hardware capture noise --seconds 10 --hz 100 --output runs/noise-001
cartpole-deploy analyze runs/noise-001/samples.csv --output runs/noise-001-quality.json
```

Read the gap, validity and angle-spread metrics. Angle spread measures noise only
when the mechanism is stationary. Encoder quantization is modeled separately;
do not blindly use the entire observed standard deviation as added Gaussian noise.
Device time controls fitting; host timing records transport delay and missed
acquisition deadlines. Neither Python polling nor requested stream rate guarantees
that rate on a loaded Jetson. Start at 100 Hz and measure it.

## 2. Passive pendulum releases

Mechanically clamp the cart at center with all drivers disabled. Driver disable
does not hold the cart. Position the arm roughly 20–40 degrees away from hanging
down, start capture, then release cleanly and keep hands clear. Collect several
releases in both directions. Mark the actual hands-off time in the trace; held
samples do not belong in the fit.

```sh
cartpole-deploy --backend hardware capture decay --seconds 12 --hz 100 --cart-clamped --output runs/decay-001
```

Each directory contains `samples.csv` and `metadata.json`. The sample time starts
at the first device observation; `theta_rad=0` is upright, ±pi is down. Inspect the
angle trace, select the first sample after hands leave, and supply its
`device_elapsed_s` to fit. For example, **only if the actual release was at 2.15 s**:

```sh
cartpole-deploy fit runs/decay-001/samples.csv --release-s 2.15 --cart-clamped --output runs/decay-001-fit.json
```

The nonlinear fit integrates the pendulum equation and estimates effective length,
equivalent viscous damping, initial release state and a diagnostic angle offset.
It rejects missing release assertions, sparse/gapped/invalid data, active drivers,
changing cart commands, insufficient excitation and unresolved oscillation peaks.
It cannot verify the physical clamp from step counts. The offset is reported but
does not silently recalibrate hardware or change simulated encoder zero.

Repeat a release at a different amplitude/direction into a separate directory and
validate with its own measured hands-off time:

```sh
cartpole-deploy validate runs/decay-002/samples.csv --fit runs/decay-001-fit.json --release-s 1.8 --cart-clamped --output runs/decay-002-validation.json
cartpole-deploy --config configs/rig-125mm.json export --fit runs/decay-001-fit.json --validation runs/decay-002-validation.json --output runs/rig-measured.json
```

Validation freezes physical parameters and the fitted offset, estimates only the
release state from the first 100 ms, and evaluates later samples. Identical file
contents cannot serve as fitting and validation data. Export changes only effective
length/damping and preserves source hashes and metrics. It remains provisional:
choose validation error tolerances from sensor noise and controller needs, inspect
residuals, and compare several releases before accepting it. No automatic
"safe for RL" verdict is produced. If residuals vary with amplitude or stop near
zero, inspect dry friction, compliance, sensor nonlinearity and release disturbance.

## 3. Bounded cart drive capture

Remove the clamp, manually center the carriage, verify the encoder and secure Z.
Use a supervised run after validating the new firmware with an unloaded drive.
The following is an explicit motion command, with a **measured example** half-span
of 0.15 m. Replace it with the smaller actual half-span when appropriate:

```sh
cartpole-deploy --backend hardware capture drive --output runs/drive-001 --seconds 10 --hz 100 --amplitude-mm 5 --frequency-hz 0.3 --execute --center-confirmed --secured-z --measured-half-span-m 0.15
```

The script homes by assertion (no search/movement), arms, sends a windowed sine
position target, returns toward center, checks that the commanded profile settles,
and stops in `finally`. A fault or deadline misses can end the run early. Partial
data and metadata remain. An unconfirmed stop makes the run fail; the firmware
lease is the independent fallback. Never automatically retry/rearm failed runs.

Start with the default 5 mm / 0.3 Hz profile. Amplitude is limited to 20 mm, the
frequency to 1 Hz, and the firmware still governs speed/acceleration/jerk. These
are commissioning caps, not tested motor-tracking limits. A commanded settle is
not evidence that the physical cart has settled.

## What still needs independent measurement

| Quantity | Available evidence | What to add |
|---|---|---|
| Pendulum effective length / damping | Encoder passive decay with cart clamped | Several amplitudes/directions and held-out releases |
| Angle noise / quantization | Stationary encoder captures | Confirm reference and angle linearity |
| Cart commanded profile | Step count and governed v/a | Already logged, not physical response |
| Tracking delay, backlash, missed steps, friction | Not identifiable from emitted steps alone | Synchronized cart encoder or calibrated camera x(t) |
| Force limit / torque-current relation | Not identified | Driver/current/force characterization under known loads |
| COM, cart mass, combined pendulum mass | Not identified by free decay | Physical measurement |
| End-to-end policy latency / jitter | Capture host timing is only one component | Instrument observation→policy→action under representative Jetson load |

For external x(t), retain its source, SI units, sample sequence, capture timestamp,
clock mapping and uncertainty alongside the run. Synchronize to the device clock
with a shared event or measured clock offset. Fit actual position/velocity against
logged requests and commanded profile before changing `actuator_time_constant_s`
or `actuator_force_limit_n`. Automated fitting of these external drive measurements
is deliberately not included until that sensor contract exists.

Before RL training, validate the dynamics on independent passive and driven data,
model measured delay/noise, and randomize within measured uncertainty. Simulation
success does not commission hardware. The included Gym task is a balance scaffold
at low owner limits, not a complete swing-up training recipe.
