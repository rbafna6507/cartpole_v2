# Encoder-only characterization and balance-policy checkpoint — 2026-10-20

The rig is stopped and disabled at counted home. Working `bw=10` gains and
`jmax=150 m/s³` are retained; saved upright count is 330. No firmware was flashed.
Vision was omitted at the operator's request because lighting was inadequate.
The camera service remains available and its temporary CPU affinity change was
restored. No learned policy was given motor authority during this session.

## What changed in simulation

Use `training/profiles/rl-encoder-20261020/`. It binds all 41 current executor
settings, the measured effective half-rail `0.309000015 m`, and the working 10 Hz
observer. The previous profile had `bw=6` and a slightly different home span.
Full HOME measured 16,507 steps; home epoch is 16. All model/executor/observation
inputs are frozen with hashes.

The existing passive law is retained: effective length 0.160303873 m, viscous
coefficient 0.006891975 s⁻¹, Coulomb angular deceleration 1.626894312 rad/s²,
smoothed with `tanh(omega/0.05)`. This effective simulation length is distinct
from the preserved controller's `leff=0.124` setting. Today's data does not justify
replacing the passive fit or claiming a measured actuator model. Cart position,
velocity and acceleration telemetry are counted/commanded values, not an
independent physical measurement of the cart.

## Measurements and limitations

Raw sealed archives are in `evidence/system-id-20261020/live/`. Both successful
and failed campaigns are retained. We completed two 25-second timing holds, a
gentle campaign containing six signed pulse/reversal tests and native AUTO, and
two independent 25-second native AUTO validation runs. A subsequent standard
campaign completed three pulses before a command-expiry fault; its separate
validation failed in the initial timing hold. Failed trials are excluded from
physics fitting, not hidden.

Near hanging, the original firmware angle origin produces poor conditional
predictions. A per-trial local hanging anchor reduces RMS on the informative
±20 mm pulse/reversal training trials to about 1.14–2.05°. It is a local
sensitivity check, not a global encoder calibration. The complete swing-up
forecasts fail the frozen model's 0.5-second accuracy checks; see
`evidence/system-id-20261020/driven-combined-v1/` for full results and plots.
The two 25-second native trials spent only 1.51 and 2.61 seconds in firmware
balance mode in total; successful run completion means collection and return
home succeeded, not sustained balancing. No physics fit was selected using
these validation runs. Subsequent finite
sign/lag checks support the existing sign on the actuator trials and do not
rescue native prediction; fixed 100 ms validation forecasts still have roughly
8.8–9.5° RMS. These checks reuse inspected validation data and are explicitly
post-hoc diagnostics, not fresh qualification.

We still need independent cart tracking with stable framing and adequate light,
and a reliable angle map across hanging, horizontal and upright. These separate
encoder geometry/zero error from physical actuator tracking and pendulum
response. A hanging-only offset cannot establish that map. The new repeated
native runs also expose full-angle/forced-motion disagreement that must be
explained before claiming a transferable swing-up simulator.

## Host timing

A recorded 53.8 ms cyclic garbage-collection pause overlapped a real deadline
failure. Powered campaign and balance CLI scopes now defer automatic cyclic GC
until STOP and disconnect; ordinary reference counting continues. Two 25-second
holds and the gentle campaign then passed, but later failures prove this is only
one mitigation. Another trace contains an approximately 10 ms wake/dispatch
pause before a 0.23 ms policy calculation. No evidence yet identifies that pause
as specifically logging, GIL contention or Linux scheduling.

The 100 Hz policy still has an observation-anchored 20 ms command lease. After
the next 10 ms sample arrives, less than 10 ms remains to renew the previous
lease. No lease, watchdog, switch, speed or acceleration guard was weakened.
The source review and measured timelines are saved with the timing evidence.

The actual exported numeric actor completed 2,501 stopped inferences over
25 seconds in the normal Jetson environment: median 1.83 ms, P99 3.58 ms,
maximum 6.50 ms. A separate CPU-affinity experiment failed on cadence after
642 inferences. Successful stopped inference does not test command renewal,
motor response, or balance quality. Powered host control remains intermittent.

## Small training comparison

Three teacher-initialized and three scratch PPO seeds received 20,480 online
training decisions each. Teacher initialization supplied useful feedback at
this budget; scratch did not establish balance. The candidate was chosen using
predeclared development ranking before eight held-out 60-second starts.
It held all eight in the nominal simulator, with about 3.71 mm tail centering
RMS. The initialized policy already held all eight, so this does not establish
a large benefit from the short PPO fine-tune.

The exported numeric SDK implementation matched PyTorch within 0.00000515 m/s²
over 24,000 actions. Two fresh nominal upright starts each held 60 seconds.
The candidate fails both ±1° encoder-bias stress cases (0/4 upright holds).
It is **balance-only, development-only, and not hardware-accepted**. It is not a
swing-up policy. A separate 30-episode teacher-gain check found that increasing
cart centering alone did not resolve the bias failures; stronger gains also
increased oscillation. No alternative was silently substituted. Recipes,
checkpoints, selection, stress results and reproduction
commands are preserved in `evidence/system-id-20261020/learning/`.

## Running the staged candidate on the Jetson

The isolated release is already staged and its `uv` environment was verified:

```bash
cd ~/cartpole-v2-live/releases/id-20261020
./scripts/run-balance-policy --help
```

For a motor-disabled artifact/inference check that also works while hanging:

```bash
uv run --locked --extra hardware python \
  evidence/system-id-20261020/tools/stopped_inference_probe.py \
  --port /dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00 \
  --actor training/candidates/balance-20261020/actor.json \
  --expected-reference 330 --seconds 25 \
  --output runs/my-stopped-inference-01
```

This never sends ARM or acceleration commands. Its output directory must be new.
A large predicted action while hanging is outside this balance-only policy's
operating region; nothing is sent to the motor.

For an **operator-supervised one-second powered experiment**, first establish a
valid direct upright reference, leave the cart centered/homed, close the console,
and step clear. Do not run while holding the pole. The pole must remain within
about 4° of the saved upright, nearly still, at admission. Use the saved count
reported by `info` if a fresh `upright` capture changes 330. Do not run `hanging`
to overwrite a good direct upright reference.

```bash
./scripts/run-balance-policy \
  --actor training/candidates/balance-20261020/actor.json \
  --port /dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00 \
  --expected-upright-raw 330 --development-only \
  --duration 1 --max-acceleration 3 \
  --log-dir runs/my-balance-01 --execute
```

Omitting `--execute` selects stopped shadow but still requires an upright start.
The 3 m/s² ceiling covers the selected nominal held-out peak raw demand of
2.942 m/s²; it is a refusal ceiling, not clipping or a validated hardware limit.
The default ceiling is a deliberately small 0.25 m/s² and will reject ordinary
balance demands. The wrapper stops on angle/rate/position/commanded-speed limits,
rail braking, changed reference, stale data, or excessive output. Its maximum
run length is 10 seconds. It never clears a fault, recenters, changes gains or
calibration, falls back to native control, or automatically retries.

The timing failures and angle-bias stress failures above remain unresolved;
this command is an experimental test facility, not a recommendation for a long
unattended run. Preserve its JSONL log and report what the cart/pole actually do.
If a new full HOME changes the measured rail, exact executor/actor admission can
refuse. Do not bypass that comparison or edit actor hashes; regenerate and
validate a profile against the new readback. Saved-home `rehome` does not change
the span, but requires valid counted home and released switches.

## Repeating data analysis

With extracted campaign directories (the archives retain their top directory):

```bash
uv run --extra id --extra plots python \
  -m cartpole_sdk.identification.driven_validation \
  --training runs/id-live-20261020/gentle-train-02 \
  --training runs/id-live-20261020/standard-train-01 \
  --validation runs/id-live-20261020/coupled-validation-01 \
  --validation runs/id-live-20261020/standard-validation-01 \
  --allow-partial --output runs/my-driven-review-01
```

`--allow-partial` admits only completed eligible trials from a failed campaign;
it does not repair the failed trial. This validator freezes the ODE and compares
predictions conditioned on recorded commanded acceleration; it does not fit or
export new physical parameters. See `docs/system-id-campaign.md` for collection,
manual angle/cart mapping and immutable review/bundle commands.
