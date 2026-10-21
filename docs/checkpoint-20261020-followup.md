# Policy guards, new characterization and robust-learning follow-up

The rig was left stopped and motor-disabled at counted home (`x=0`, fault 0),
with reference 330, home epoch 18, both cart switches enabled, jerk 150 m/s³ and
all original settings restored. The characterization used `bw=8`; handoff
restored `bw=10` for the existing balance actor. No firmware was flashed and
no encoder reference was rewritten. Vision was omitted at the user's request.

## Why the one-second balance trial stopped

The preserved log contains seven actions over 70 ms. It started at an observed
+1.58°; at STOP it was −2.29°, with counted cart displacement 2.025 mm and
commanded velocity 0.0398 m/s. The only crossed wrapper state limit was angular
rate: −1.345 rad/s versus the commissioning bound of 1 rad/s. There was no rail
braking or board fault in that trial. This establishes the immediate refusal,
not whether physical pose, encoder offset, model mismatch or policy quality
caused the transient. See [the trace](../evidence/balance-error-20261020/operator-trial/guard-trip.png).

## Running with the rig's motion envelope

The tested update is installed in `~/cartpole-v2-live/releases/id-20261020`.
It adds explicit `--guard-profile rig`, removing commissioning angle/rate
cutoffs and allowing native braking. Counted rail/speed bounds, native switches,
acceleration/jerk governors, reference/parameter matching and stale-command STOP
remain active. Duration can be up to 60 s; acceleration authority is still an
explicit CLI choice. The old balance-only actor still needs an upright start.

```sh
cd ~/cartpole-v2-live/releases/id-20261020
./scripts/run-balance-policy \
  --actor training/candidates/balance-20261020/actor.json \
  --port /dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00 \
  --expected-upright-raw 330 --development-only \
  --guard-profile rig --duration 10 --max-acceleration 25 \
  --log-dir runs/my-balance-rig-01 --execute
```

Use a new log directory for each experiment. Close the console before running;
start centered, nearly still and upright, and step clear. Omitting `--execute`
performs stopped shadow inference. The command above grants the actor the full
configured acceleration ceiling; the native governor still applies. It does
not make the balance actor capable of learned swing-up. The new profile was
verified through local integration tests and remote artifact loading, not a
powered run of that actor. [All profile details](balance-guard-profiles.md).

If a console command changed `bw` to 6 or 8, restore 10 before using that existing
actor. Training a copied bw=8 profile is separate from rewriting an old actor's
snapshot. For native control, the user's successful `bw=8` setting remains a
separate choice in the normal console.

## Collected data and what it says

Raw archives and analysis are under `evidence/balance-error-20261020/`.
The new archive contains four sealed campaigns, all verified locally, including
failed attempts. Eleven of twelve standard signed pulse/reversal trials
completed. The initial 25 s timing hold and the final negative 60 mm reversal
stopped on action-lease expiry. Their incomplete trials are excluded from
physics scoring. Three native 25 s AUTO trials completed, including two separately
labeled validation runs. Each validation run reached firmware balance at about
2.5 s and stayed there for the remaining 22.5 s, then returned to saved home.
The two identified timeouts were cleared only while stopped, with released
switches and unchanged reference/home, before separate collection sessions.

The user's earlier 55 s native logs are also preserved: bw=6/bw=8 captured at about
5.44/2.49 s and stayed in balance mode for 49.55/52.51 s. They still show substantial
cart travel and mean negative counted position; long mode 3 duration does not
mean centered or motionless balance. [Native comparison](../evidence/balance-error-20261020/native-success/native-auto.png).

The unchanged passive model gives local-hanging-anchor 0.5 s prediction RMS of
roughly 0.94–3.18° on most informative short actuator trials. Faster positive
30 mm/40 mm trials reach 6.83°/6.45°. The two native validation runs have roughly
70° pooled RMS over predictions out to 0.5 s. The model receives future recorded commanded
acceleration, and each forecast restarts from past/current sensor samples;
these are conditional forecasts, not full free-running simulation. Upright
instability, noisy rate initialization, encoder mapping and physical actuator
response remain confounded. The recorded controller does not correct forecast
deviations during this open-loop replay. A local hanging phase is not a global
calibration. In wholly balance-mode windows, exact 10 ms predictions have about
1.19°/1.49° RMS; errors grow strongly with horizon and depend on initial rate.
The 0.5-second forecast pipeline performs poorly near upright, but this does
not isolate physical plant-model error. The separate shorter-horizon audit
retains both causal-rate and firmware-rate results without changing the frozen
model or original scores.
[Horizon audit and plot](../evidence/balance-error-20261020/horizon-audit/README.md).

No physical parameters were promoted into the Gym/MuJoCo model from these
records. In particular, counted position and commanded acceleration are not
independent measurements of actual cart motion. The current model remains a
useful development model with a passive fit, not a validated full-rig simulator.
[Measured versus predicted validation](../evidence/balance-error-20261020/driven-validation/validation-1-1-prediction.png).

The timing failures occurred with GC already deferred and a simple feedback
policy. They therefore cannot be attributed only to neural inference or GC.
One quiet-policy trace reached 8.97 ms from host receipt to completed command
write; this omits earlier board-to-host age. The 100 Hz loop's 20 ms source-anchored
lease remains intermittent on this host. Wider commissioning bounds and domain
randomization do not resolve that timing path.

The final slow two-switch HOME repeated the previous 16,506-step span. Its final
stationary contacts were −0.3094875 m and +0.3094875 m in the old counted frame,
matching the old endpoints at the logged resolution. All 41 settings stayed
unchanged, reference 330 survived, and the board ended disabled at home, fault 0.
This single audit finds no net endpoint/count discrepancy; it cannot establish
physical metric scale, transient lag or absence of canceling missed steps.
[Homing plot](../evidence/balance-error-20261020/home-audit/home-audit.png).
The complete raw audit is separately preserved in `live/home-audit-20261020.tar.gz`.

## Reproduce the collection and analysis

The existing collector scripts remain the entry points. The recorded sessions
used the following commands on the Jetson after stopped preflight and an explicit
`bw=8` write. Retain a valid direct upright reference; do not replace it with an
ideal hanging zero. New collection needs the rig clear and the console closed.

```sh
PORT=/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00
./scripts/system-id-campaign collect --suite actuator --level standard \
  --repetitions 1 --port "$PORT" --execute --encoder-only \
  --expected-reference 330 --expected-home 17 --dataset-role training \
  --run-label bw8-actuator-training --output runs/NEW-actuator-training
./scripts/system-id-campaign collect --suite coupled --seconds 25 \
  --repetitions 2 --port "$PORT" --execute --encoder-only \
  --expected-reference 330 --expected-home 17 --dataset-role validation \
  --run-label bw8-coupled-validation --output runs/NEW-coupled-validation
```

The identity pins above describe the collected campaigns. A later full-HOME
audit advanced the live home epoch to **18**, so use `--expected-home 18` for
new collection unless a subsequent HOME changes it. Read `info` before running. On any
fault the collector aborts; it does not silently clear or retry.

After extracting `live/id-followup-20261020.tar.gz` in the project root:

```sh
uv run --extra id --extra plots python -m cartpole_sdk.identification.driven_validation \
  --training runs/id-followup-20261020/actuator-training-01 \
  --training runs/id-followup-20261020/coupled-training-01 \
  --validation runs/id-followup-20261020/coupled-validation-01 \
  --allow-partial --output runs/NEW-followup-analysis
```

`--allow-partial` scores only completed eligible trials, never the failed trial.
The script verifies sealed input hashes, plots predictions, and does not export
or silently fit a replacement model.

## Remaining measurements

1. **Physical cart tracking during the signed pulses/reversals:** fixed camera,
   adequate light, full rail and markers, plus ruler anchors from `cart-map`.
   This distinguishes actuator gain, lag, directional effects and missed motion
   from internal step/command estimates. Once the anchors and framing are ready,
   the powered `actuator` and `coupled` collections can run autonomously with
   camera recording (omit `--encoder-only`).
2. **Independent angle poses in both approach directions:** `angle-map` records
   hanging, intermediate, horizontal and upright poses. Actual measured angles
   distinguish zero error, nonlinear encoder mapping and approach hysteresis.
   A naturally resting pose alone cannot establish all of these.
3. **Small releases near upright with the cart restrained:** `capture-friction`
   records ±5/10/20° releases. These probe static/low-speed friction where the
   passive hanging fit may not describe capture and balance. This is a useful
   next measurement, not an identified explanation for today's mismatch.

These three require physical setup or handling and were not fabricated from
encoder-only data. [Guided commands](system-id-campaign.md) already exist. The
host timing trace is an additional software reliability task, separate from
physical parameter fitting.

## Learning work

The first completed upright-only pilot compared two matched seeds at 4096
training decisions with and without ±1° constant actor-input bias. Both arms
retained nominal balance, but both achieved 0/16 holds on nonzero-bias development
cases. This small experiment does not show that domain randomization cannot
work; it shows no improvement at that budget. Its recipes/checkpoints/replay CLI
are preserved in [the angle-error report](../evidence/balance-error-20261020/angle-error-learning/README.md).

The separate full-task experiment uses the preserved learned swing-up actor as
initialization, copied into a new bw=8 experiment with a fresh critic/optimizer.
It compares nominal training against ±2° persistent actor-input offsets plus
length/friction/noise/delay variation. Training and evaluation use both hanging
and upright starts. These are declared engineering ranges, not uncertainty
bounds identified by the new hardware data. The prior actor's old-profile result
was 5/8 fresh hanging and 8/8 upright 60 s cases; those results do not transfer
automatically to the new profile. See `scripts/robust-swing-learning --help` and
`evidence/robust-swing-20261020/README.md` for the completed pilot and reproduction.


The full-task pilot is now complete: four runs, 81,920 training decisions and
168 evaluation episodes. Each run saw only eight complete training episodes.
On the final held-out pose, each arm held 1/2 hanging starts and 2/2 upright starts
across optimizer seeds. Neither arm met the final-five-second balance/centering
criterion on any of the 24 biased/combined cases in that split. All episodes
completed without simulator faults; failure of the hold criterion is not a
claim of a simulated crash. Randomization retained more development swing-up
than nominal training, but did not demonstrate the required angle-error
robustness. No new hardware actor was exported or selected.
