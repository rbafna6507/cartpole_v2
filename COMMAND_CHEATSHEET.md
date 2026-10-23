# Cartpole command cheat sheet

Current operator workflow: October 23, 2026. Full system explanation: [SYSTEM_README.md](SYSTEM_README.md). Every captured CLI option/subcommand: [COMMAND_REFERENCE.md](COMMAND_REFERENCE.md). Historical commands remain in their dated evidence; use the commands here for the new operator release.

## Start the Jetson console

```bash
ssh rbafna@jetson
cd ~/cartpole-v2-live/active
~/.local/bin/uv run --locked cartpole
```

With `~/.local/bin` on PATH, use `uv run cartpole` in that directory, or `cartpole-console` from any directory. The installed PATH wrapper changes into the selected release. `uv run cartpole` itself keeps your current directory, so relative profile/actor paths resolve there.

The launcher supplies the installed Teensy's by-id path, 250 Hz telemetry, `--keep-board-params`, a scoped 1 ms Python GIL interval, camera CPUs 0–3, control CPUs 4–5, and child SCHED_RR priority 10. It preserves the running camera service and restores its temporary affinity after the console exits. If this login has no realtime allowance, the launcher requests your sudo password for **only** `prlimit` on its own process; the console runs as your normal user. It does not grant persistent root access or change login limits. No firmware flash is needed.

```bash
# Inspect the command without serial access, sudo or affinity changes:
uv run cartpole --dry-run
uv run cartpole --help

# Override the device or telemetry rate:
uv run cartpole --port /dev/ttyACM0 --rate 100

# Explicitly restore a saved parameter profile rather than keeping board RAM:
uv run cartpole --startup-profile src/cartpole_sdk/control/tuned-20261016-bw10.json

# Explicit diagnostic mode without realtime/CPU partitioning:
uv run cartpole --no-affinity --rt-priority 0 --command info
```

Use an existing profile path; the maintained built-in bw10 profile is `src/cartpole_sdk/control/tuned-20261016-bw10.json`. `--startup-profile` does not calibrate the encoder or HOME. The lower-level `python -m cartpole_sdk.rig.console` still has its original required `--port` and default-profile behavior; the convenient launcher deliberately keeps live parameters unless overridden.

| Launcher option | Default / meaning |
|---|---|
| `--dry-run` | Print JSON launch plan only |
| `--rt-priority N` | 10; range 0–99; 0 explicitly disables realtime |
| `--no-affinity` | Disable CPU partitioning; does not itself disable realtime |
| `--no-camera` | Apply control affinity only; intentionally skip camera affinity |
| `--camera-service NAME` | `cartpole-vision.service` |
| `--camera-cpus LIST` | `0-3`; comma-separated numbers/ranges |
| `--control-cpus LIST` | `4-5`; must be available and disjoint from camera CPUs |
| `CARTPOLE_PORT` environment variable | Default device override; explicit `--port` wins |
| `-h`, `--help` | Launcher and console option help; no device access |

## Load and run a learned policy

Your October 23 report establishes successful physical swing-up for the 102,400-step actor. It remains the explicit `working` alias. The newer 1,024,000-step actor is `1m`; it is staged for your trial, not automatically promoted over the working actor.

```text
status
rehome
```

Use `home` instead of `rehome` if no valid home exists. Wait for completion, centered cart and a settled hanging pole; retain the valid saved upright calibration. Then:

```text
policy load policies/working.json
policy check swingup
policy swingup 25
```

To try the million-step candidate after another explicit `rehome` and settling:

```text
policy load policies/1m.json
policy check swingup
policy swingup 25
```

The explicit original paths remain valid:

- Working: `training/candidates/combined-recovery-20261021-step000102400-rail1mm/actor.json`
- Million-step: `training/candidates/combined-recovery-20261023-step001024000-rail1mm/actor.json`

`policy check swingup` does not move the cart. `policy swingup` runs the same network through capture and balance. Ctrl-C stops the learned invocation and returns to the prompt. Expiry stops; it does not automatically rehome. `policy run` is still upright-start only. Do not use `hanging ideal` as preparation for these policies.

## Interactive console commands

| Command | Arguments / behavior |
|---|---|
| `help`, `?` | Show commands |
| `status`, `info` | Telemetry and stopped firmware/reference diagnostics |
| `stop`, `clear` | Disable; separately clear a healthy stopped fault |
| `home`, `rehome` | Physical two-end homing; return to saved counted center |
| `center` | Explicit switchless physical-center assertion; no movement |
| `switches on\|off` | Enable installed interlocks or explicit stopped commissioning bypass |
| `upright` | Stable physically upright calibration, saved/read back |
| `hanging ideal` | Explicit ideal half-turn assumption; unsuitable as an automatic substitute on this rig |
| `hanging MODEL IDENTITY` | Approved installation-bound hanging model; no accepted model presently exists |
| `auto [SECONDS]` | Native AUTO, default 10 s; v6 normal expiry returns to center |
| `bal [SECONDS]`, `balance [SECONDS]` | Native upright balance, default 10 s |
| `python-auto [SECONDS]`, `python-bal [SECONDS]` | Experimental host control, default 10 s |
| `manual [SECONDS]` | Bounded manual mode, default 10 s; action lease still applies |
| `velocity M_PER_S [TTL_MS]` | One velocity lease; default 50 ms; no automatic renewal |
| `rate HZ` | 0, 100, 250, 500 or 1000 Hz telemetry |
| `params`, `get NAME`, `set NAME VALUE` | Read/read one/set a stopped RAM parameter; all 41 parameters in system README |
| `save PATH`, `load PATH` | Save/apply a verified parameter profile; quote paths containing spaces |
| `policy load PATH`, `policy unload`, `policy status` | Select/remove/inspect actor; loading never arms |
| `policy check [swingup]` | Validate current upright or hanging start without motion |
| `policy shadow [swingup] [SECONDS]` | Motor-disabled inference; default 5 s upright, 25 s hanging |
| `policy run [SECONDS]` | Upright learned execution, default 5 s |
| `policy swingup [SECONDS]` | Hanging learned execution, default 25 s |
| `quit`, `exit` | STOP and close |

Learned invocation maximum is 60 s. Native HOME/REHOME commands return to the interactive prompt while the board works; wait for completion before the next stopped-only command. Python and learned invocations occupy the prompt. Outside learned run/shadow, Ctrl-C exits with STOP cleanup.

### Console shell arguments

All pass through `cartpole` / `cartpole-console`; full help is in the argument reference.

| Option | Values / purpose |
|---|---|
| `--port PATH` | Device; launcher supplies the installed by-id device by default |
| `--rate HZ` | 0, 100, 250, 500, 1000; launcher default 250 |
| `--log-dir PATH` | Default `runs/rig` |
| `--vision-telemetry-port PORT` | Default 3096; 0 disables |
| `--no-vision-telemetry` | Disable encoder UDP mirror |
| `--command NAME` | One-shot: auto, bal, manual, velocity, stop, center, home, rehome, upright, hanging, status, info, clear, params, get, set, save, load, policy-zero, policy-run, python-auto, python-bal |
| `--duration SECONDS` | Default 10; learned 5; HOME timeout 75; REHOME timeout 15.25 |
| `--actor PATH`, `--development-only` | Both required for one-shot `policy-run` |
| `--switches on\|off`, `--center-confirmed` | Explicit stopped commissioning changes |
| `--param NAME`, `--value NUMBER` | One-shot get/set |
| `--profile PATH` | One-shot save/load |
| `--startup-profile PATH`, `--keep-board-params` | Mutually exclusive startup behavior; launcher defaults to keeping board RAM |
| `--velocity NUMBER`, `--ttl-ms N` | Manual one-shot values, defaults 0 and 50 ms |
| `--source magnetic-step` | Required for external policy-zero/python-auto/python-bal; host controllers require rate 100 or 250 |
| `--hanging-model PATH`, `--calibration-identity PATH` | Pair required for model-based one-shot hanging calibration |
| `--ideal-half-turn` | Alternative explicit one-shot hanging assumption |

## View simulation locally

From `/Users/rbafna/projects/cartpole_v2`:

```bash
# Proven 102400-step learned actor, actual training Gym loop:
uv run --locked --extra sim cartpole-view-policy

# Million-step candidate:
uv run --locked --extra sim cartpole-view-policy --actor policies/1m.json

# Traditional saved gains on the same fitted physical plant:
uv run --locked --extra sim cartpole-view-policy --controller reference

# Upright start, another seed, longer simulation:
uv run --locked --extra sim cartpole-view-policy --start upright --seed 98401 --seconds 60

# Same episode without a GUI:
uv run --locked --extra sim cartpole-view-policy --headless --seconds 25

# Existing generic reference demo remains separate:
uv run --locked --extra sim cartpole-v2-view --start auto --seed 0
```

`./scripts/view-policy ...` is an equivalent wrapper. macOS automatically uses `mjpython`. Space pauses/resumes, R resets the same seed, Esc closes. At horizon/fault, the episode freezes until reset. Mouse physics edits are display-only; camera manipulation is fine. Learned mode runs the actual 100 Hz Gym policy loop; traditional mode uses the saved gains at 1 kHz with ideal sensors. These are explicitly different sensor/execution paths.

| Viewer option | Default / values |
|---|---|
| `--controller learned\|reference` | `learned` |
| `--actor PATH` | Preserved 102400-step rail1mm actor; ignored in reference mode |
| `--experiment PATH` | Original combined protocol's embedded experiment; same experiment as the dated source-binding derivative |
| `--start hanging\|upright` | `hanging` |
| `--seed INTEGER` | 98400, nonnegative |
| `--seconds NUMBER` | 25; 0.01–60 in whole 100 Hz decisions |
| `--duration NUMBER` | Optional positive wall-clock window timeout |
| `--headless` | Run episode and print JSON without GUI |
| `-h`, `--help` | Complete help |

The older `cartpole-v2-view` accepts `--start auto|upright`, `--seed` (0), and optional `--duration`. Its model/default tuning is the earlier generic demo; use `cartpole-view-policy --controller reference` for the fitted-plant comparison.

## Start a training loop

Use the dated protocol for this source release; the historical protocol deliberately refuses source-hash mismatches. Training is local simulation only. Output directories must be new. No cloud training was started by this release work.

```bash
# Short wiring/smoke run:
uv run --locked --extra rl python evidence/policy-recovery-20261021/combined-next/run.py train \
  --protocol training/protocols/combined-operator-20261023.json \
  --arm ppo --seed 11 --budget pilot --smoke --output runs/combined-smoke-new

# Full projected-PPO run:
uv run --locked --extra rl python evidence/policy-recovery-20261021/combined-next/run.py train \
  --protocol training/protocols/combined-operator-20261023.json \
  --arm ppo --seed 11 --budget long --output runs/combined-ppo-seed11-new

# Actor-retention variant: use --arm retained and a distinct output directory.
```

| `train` option | Values / behavior |
|---|---|
| `--protocol PATH` | Explicit dated protocol recommended; historical default is frozen to old source |
| `--output PATH` | Required new run directory |
| `--arm ppo\|retained` | Required; projected equilibrium PPO or actor-retention PPO |
| `--seed INTEGER` | Required optimizer seed declared in protocol (11, 23, 47) |
| `--budget pilot\|long` | Default pilot; budget comes from protocol (pilot 102,400; long 1,024,000 steps) |
| `--smoke` | Short execution check, reduced rollout/batch/epochs; not a quality trial |

Evaluate a checkpoint from a completed run made with the same protocol:

```bash
uv run --locked --extra rl python evidence/policy-recovery-20261021/combined-next/run.py evaluate \
  --protocol training/protocols/combined-operator-20261023.json \
  --run runs/combined-ppo-seed11-new --step 1024000 \
  --output runs/combined-ppo-seed11-eval --numeric
```

`evaluate` requires `--run`, `--step`, and new `--output`; optional `--protocol`, `--numeric` (exported NumPy inference), `--stress` (declared perturbations), and `--confirmation` (reserved seeds, 60 s rather than 25 s). Do not use confirmation repeatedly to select checkpoints. Historical recovered checkpoints require their recorded recovery/export path; do not pretend they were trained under the new protocol.

General preparation/training/evaluation tools remain available: `scripts/prepare-training-model`, `prepare-rig-training`, `train-ppo`, `balance-learning`, `balance-error-learning`, `swing-learning`, `robust-swing-learning`, `swing-transfer-check`, `rl-diagnostics`, `replay-balance-evaluation`, `prepare-colab-training`, and `colab-training`. Their complete help and subcommands are in [COMMAND_REFERENCE.md](COMMAND_REFERENCE.md). These are separate research workflows; they do not all reproduce the combined-policy recipe above.

## Build and deploy future operator releases

Commit and push source first. Use a new release name each time. Build only trusted owner-controlled source; this installer is not the public submission sandbox.

```bash
# Local checkout; clean tracked source required:
python3 scripts/cartpole-release build --name operator-YYYYMMDD-NAME \
  --output /tmp/cartpole-operator.tar.gz > /tmp/cartpole-operator-manifest.json
scp /tmp/cartpole-operator.tar.gz src/cartpole_sdk/release.py rbafna@jetson:/tmp/

# Jetson; install, verify actors offline, then select active and install PATH wrappers:
ssh rbafna@jetson 'python3 /tmp/release.py install \
  --archive /tmp/cartpole-operator.tar.gz --root /home/rbafna/cartpole-v2-live \
  --uv /home/rbafna/.local/bin/uv --python /home/rbafna/.local/bin/python3.11 \
  --bin-dir /home/rbafna/.local/bin'
```

The bundle contains maintained runtime, scripts, profiles, policy candidates/aliases, docs, examples, firmware source, and required protocol inputs. It excludes historical raw runs, caches, virtual environments, and most archival evidence; use GitHub/full preservation backups for those. The installer checks the complete member inventory/hashes, creates a new release directory, installs locked lightweight operator dependencies, checks both actors and the launch plan without serial access, and switches `active` only after success. It neither restarts an existing console nor changes the camera service. A failed installation is retained for diagnosis and cannot overwrite an existing release name.

`build` options: required `--name`, `--output`; optional `--repo` (current directory). `install`: required `--archive`; optional `--root` (`~/cartpole-v2-live`), `--uv` (`~/.local/bin/uv`; use an absolute path), `--python` (`3.11`; use an absolute path for a custom interpreter), `--no-activate`, `--bin-dir` (omit to skip PATH wrappers). `activate`: required `--name`, optional `--root`; accepts only previously verified releases.

```bash
# Select a previously verified release, without launching hardware:
python3 scripts/cartpole-release activate --name operator-YYYYMMDD-PREVIOUS

# Historical pre-installer release remains available directly:
cd ~/cartpole-v2-live/releases/id-20261021-policy-swingup
# Use its recorded launcher instructions in its POLICY-SWINGUP.md.
```

The old `current` directory is left intact. `active` is the new explicit pointer. Stop/quit an old console before starting another; deployment itself does not take serial ownership.

## Camera viewing and diagnostics

The existing user service is independent of the operator release:

```bash
ssh rbafna@jetson 'systemctl --user status cartpole-vision.service --no-pager'
ssh rbafna@jetson 'journalctl --user -u cartpole-vision.service -n 80 --no-pager'
./scripts/vision-tunnel.sh
```

The tunnel exposes the loopback dashboard at `http://127.0.0.1:3090`. Its wrapper accepts an optional SSH destination and local port arguments (`./scripts/vision-tunnel.sh HOST PORT`); defaults are `rbafna@jetson` and `3090`. Use the existing service rather than starting a second camera process. All standalone `cartpole-vision` camera, frame-rate, encoding, calibration, recording and telemetry options are captured in the argument reference. The new operator release does not deploy the local camera-specific fix or restart the service.

## Tests and offline checks

```bash
uv sync --locked --all-extras
.venv/bin/python -m pytest -q
uv run cartpole --dry-run
uv run --locked --extra sim cartpole-view-policy --headless --seconds 2
```

For development, `uv run` may synchronize away extras not requested on that invocation. Use `uv sync --locked --all-extras` before the full suite or `.venv/bin/python` to use an already prepared environment without re-sync. The default `operator` dependency group supplies NumPy/pyserial for plain `uv run cartpole`; simulation and RL remain explicit extras.

## Controller development and read-only sensor viewing

See [the developer guide](docs/CONTROLLER_DEVELOPER_GUIDE.md) for sensor units, raw versus filtered values, timing, SDK examples and current portal limitations. On the Jetson, with the camera service and console encoder mirror running:

```bash
curl --no-buffer 'http://127.0.0.1:3090/api/sensing-stream?max_hz=100'
```

This display stream is bounded and best-effort; submitted controllers receive SDK observations directly from the trusted worker. The local portal UI accepts an operator credential to approve each waiting physical job. Approval never prepares or arms hardware by itself.
