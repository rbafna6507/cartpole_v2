# Model-bound PPO training

MuJoCo computes the cart-pole physics. Gymnasium gives the learner a standard
environment interface. PPO, from Stable Baselines3, trains the neural policy.
The older `examples/train_policy.py` is CEM search over ten gains of a handwritten
controller. It remains a useful baseline and is not neural-network training.

The new `examples/train_ppo.py` runs on a laptop or Google Colab, with no device
connection. It uses `RigCartpoleEnv`: 1 ms physics and governor ticks, 100 Hz policy
decisions, explicit executor parameters, encoder quantization, the causal firmware
angle/rate observer, and configured telemetry/command delays. It preserves the
ideal acceleration-servo assumption; force saturation ends a rollout because
physical tracking beyond that point is unsupported. No motor, slip, backlash or
disabled-motor stopping model is claimed.

## Model qualification comes first

Use the [collection, fitting and export workflow](system-identification-workflow.md)
to produce a content-hashed model export. A rejected fit cannot be used as an
identified model, and this trainer does not bypass the export gate. Non-unit input gain and input delay still require explicit plant support.
The plant now supports smooth dry friction through
`hinge_coulomb_friction_nm` and `hinge_friction_velocity_scale_rad_s`. The older
sign/stiction fit report has different near-zero behavior and is still rejected
by the identified exporter; it is not silently reinterpreted as the smooth law.

The current model export scopes are `passive-down` and `driven`. Neither certifies
global swing-up/balance or hardware transfer. Consequently this version requires
the conspicuous `--development-only` flag for those scopes and records
`task_qualified=false` and `hardware_accepted=false`. The flag permits exploratory
simulation only; it does not turn a rejected fit into a valid export. A future
global-qualification schema needs independently validated task coverage. The frozen experimental profile below is usable for development training while
its remaining measurement and driven-model qualifications are documented.

There is also a separate `cartpole-development-model-v1` format for explicit experimental
models and software tests. Its required fields are `status: "DEVELOPMENT_ONLY"`, a complete
`simulation_config`, nonempty `rationale` and `limitations`, and `content_sha256`
(SHA-256 of canonical sorted compact JSON before adding the hash). It has no
accepted-fit claim and is never an identification export.

## Installed passive-friction training profile

`training/profiles/passive-20261017` contains ready-to-use model, executor,
observation and prior inputs. Its source is the frozen batch-6 fit, checked on
batch 7 before this integration. Both training- and validation-labelled files
from batches 8/9 were then checked as validation without refitting: all 47
observed releases pass the short-forecast numeric/coverage checks, with
continuous recording RMS of 2.85-4.06 degrees. Camera/pose qualifications remain
unresolved; see the [complete comparison](../evidence/passive-batches8-9-20261017/README.md).
The profile is not automatically refitted when new recordings arrive.

The model uses L_eff=0.160303873 m, gamma=0.006891975/s and smooth dry-friction
acceleration 1.626894312 rad/s². With assumed pole mass 0.02275 kg,
`I_pivot=0.75*m*L_eff²`, the backend applies `-I*c*tanh(omega/0.05)` at every
1 ms tick and includes it in cart-force compensation. Both Gym environments
use that backend. Loading the generated MJCF by itself omits this applied torque.

The recorded executor inspection supplies rail half-span 0.308962494 m,
jerk 150 m/s³ and observer bandwidth 6. Controller gains remain the recorded
values; their .124 m policy prior is explicitly separate from the fitted plant
length. The development profile declares 3 ms telemetry delay and 1 ms command
delay, quantized encoder readings, zero additional noise and no dropout.
Those timing/noise choices, cart mass, damping and force authority remain
assumptions. They should be varied before judging transfer robustness.

Run a short local training trial, then increase `--steps` for a substantive run:

```bash
PROFILE=training/profiles/passive-20261017
./scripts/train-ppo train \
  --model "$PROFILE/model.json" \
  --executor-parameters "$PROFILE/executor-parameters.json" \
  --observation-config "$PROFILE/observation-config.json" \
  --prior-parameters "$PROFILE/prior-parameters.json" \
  --development-only --training-seeds 11 12 13 --seed 20261017 \
  --steps 100000 --seconds 25 --output runs/ppo-friction-001
```

The same four files work with the headless Colab CLI instructions below. To
create the input archive used there:

```bash
zip -j cartpole-inputs.zip \
  training/profiles/passive-20261017/model.json \
  training/profiles/passive-20261017/executor-parameters.json \
  training/profiles/passive-20261017/observation-config.json \
  training/profiles/passive-20261017/prior-parameters.json
```

Use a new ZIP filename if it already exists. Keep the complete profile folder
with your local evidence; `bundle.json` hashes all generated inputs and the
copied freeze retains original quality flags. This profile makes no accepted-fit
or hardware-approval claim. The trainer requires `--development-only` explicitly.

Rebuild the profile into a new directory (or use different explicit assumptions):

```bash
./scripts/prepare-training-model \
  --freeze evidence/system-id-model-review-20261017/candidate-freeze-latest6.json \
  --executor-parameters training/inputs/passive-20261017/executor-parameters.json \
  --observation-config training/inputs/passive-20261017/observation-config.json \
  --assumptions training/inputs/passive-20261017/assumptions.json \
  --output runs/my-friction-training-profile
```

This command validates the frozen coefficient/parameter mapping, converts torque
units, preserves source hashes and writes an immutable development bundle. It
does not collect data or refit the pendulum. Complete legacy zero-friction model
configs remain readable; partially specified new friction configs are rejected.

## Prepare four explicit inputs

Keep these together with the fitting evidence:

- `model.json`: the immutable identified export, including fit report and scope.
- `executor-parameters.json`: a complete recorded `ControllerParameters` object,
  or a `Rig.save_parameters()` profile with `schema_version: 1` and `parameters`.
  Missing settings are rejected. The model and executor rail must match.
- `observation-config.json`: every field of `RigObservationConfig`, including the
  raw/filtered angle selection, encoder resolution, noise, delays and dropout.
  These are declared assumptions until measured.
- `prior-parameters.json`: every field of `HostPolicyParameters`. This is an
  explicit comparison prior, not action labels or neural pretraining. Its
  effective length is recorded separately from the plant length.

For example, after saving a complete executor readback, this writes explicit
starting assumptions for review. It does not connect to or modify the rig:

An existing `scripts/system-id inspect` report contains the actual readback in
its `result.parameters` field. Extract it without replacing missing fields with defaults:

```python
import json
from pathlib import Path
inspection = json.loads(Path('runs/inspection-01/report.json').read_text())
Path('executor-parameters.json').write_text(json.dumps(inspection['result']['parameters'], indent=2))
```

Use the report corresponding to the model's recorded setup. This extraction
does not make the old snapshot current; retain its firmware/reference/time
metadata with the experiment evidence.

```python
import json
from dataclasses import asdict
from pathlib import Path
from cartpole_sdk.control.parameters import ControllerParameters
from cartpole_sdk.policies import HostPolicyParameters
from cartpole_sdk.sim.rig_gym_env import RigObservationConfig

profile = json.loads(Path('executor-parameters.json').read_text())
values = profile['parameters'] if profile.get('schema_version') == 1 else profile
parameters = ControllerParameters(**values)  # Trainer separately requires all fields.
observations = RigObservationConfig(
    angle_source='raw', encoder_counts=4096, angle_noise_std=0.,
    telemetry_delay_steps=0, command_delay_steps=0, dropout_probability=0.)
prior = HostPolicyParameters.from_controller(parameters)
Path('observation-config.json').write_text(json.dumps(asdict(observations), indent=2))
Path('prior-parameters.json').write_text(json.dumps(asdict(prior), indent=2))
```

Zero noise/delay in this example is an explicit development assumption. Observer
bandwidth comes from the executor snapshot; it is not replaced with perfect
angular velocity. Reset starts the observer at zero rate and obtains the first
healthy snapshot through causal pre-arm warmup under the 20 ms lease. The plant
continues to evolve during that delay. Later unavailable or stale policy input
ends the episode; ground truth is never substituted into actor features.

## Train, save and resume

Install only on the training machine. The `rl` extra includes MuJoCo, Gymnasium,
NumPy, Torch and Stable Baselines3. Base and hardware-only installations do not
gain neural dependencies. The separate `plots` extra is for recording review.

```sh
./scripts/train-ppo train \
  --model runs/model.json \
  --executor-parameters runs/executor-parameters.json \
  --observation-config runs/observation-config.json \
  --prior-parameters runs/prior-parameters.json \
  --development-only --training-seeds 11 12 13 --seed 20261017 \
  --seconds 10 --steps 2048 --n-steps 1024 --batch-size 64 --epochs 10 \
  --checkpoint-every 1024 --output runs/ppo-001
```

Start with this small execution check, then choose a larger training budget in a
new run. Steps must be a multiple of `n-steps`; batch size must divide it. The
implementation uses one CPU environment, a 64×64 tanh actor and value network,
and a fixed training seed pool spanning hanging/upright initial-state families.
No domain randomization is currently implemented. Fit standard errors are
conditional regression uncertainties, not a complete plant posterior.
PPO uses a 0.99 discount factor during optimization; the reported evaluation
score is the undiscounted finite-episode benchmark used for controller comparison.

Each run contains `experiment.json`, `manifest.json`, `checkpoint.zip`, numeric
`actor.json`, and periodic checkpoint directories. The manifest records model
content/file/fit hashes, scope, assumptions, full simulation/executor/observation
settings, algorithm settings, seeds, versions and source hashes. It records the
actual number of steps. Outputs are immutable; choose a new directory per run.
Keep the original model and input JSON files with the run.

Resume by repeating the same command with a new output and
`--resume runs/ppo-001`. `--steps` is the additional budget. Model, input settings,
seed pool, algorithm settings, source hashes and dependency versions must match.
Moving identical input files to another directory is allowed. Optimizer state
and timestep count continue; episodes restart from the fixed training pool, so
this is not a promise of bitwise equivalence to uninterrupted training. Only
load SB3 archives you created or trust: their format includes serialized Python
objects. Numeric `actor.json` does not contain executable serialization.

## Frozen evaluation and SDK inference

Evaluate after freezing the checkpoint. The evaluator rejects training-seed
overlap, never updates weights, and reports every hanging/upright episode:

```sh
./scripts/train-ppo evaluate runs/ppo-001 \
  --seeds 1001 1002 1003 1004 1005 1006 --output runs/ppo-001-heldout.json
```

Metrics include reward, final continuous balance time, success, peak cart travel
and speed, saturation, braking and faults. Success requires the full last second
inside the declared x/angle/rate bounds and no fault. A short smoke run cannot
establish success. Preserve final test seeds; changing the policy after inspecting
them makes them development data, requiring a new held-out set.
The training horizon is an actual terminal condition for this finite objective,
so SB3 does not bootstrap a continuing value past the final balance-time bonus.

The actor consumes the same shared encoding of six explicit SDK channels as the
simulator: x, commanded velocity, angle, filtered angular velocity, commanded
acceleration and brake direction. Angle becomes sine/cosine, yielding seven
state features plus masks and ages. PPO predicts a scalar in [-1,1], mapped once
to raw acceleration in m/s². The trusted executor governs that demand once.

```python
from cartpole_sdk.policies.neural import load_neural_policy
from cartpole_sdk.policies.rig_observation import rig_channels

# Factory only: this does not open a device, arm, or approve hardware use.
policy = load_neural_policy('runs/ppo-001/actor.json',
                            channels=rig_channels(angle_source='raw'))
# Trusted runner calls policy.reset(session), then
# policy.act(rig.control_observation()) -> Acceleration or None.
```

Use `Rig.control_observation()` for the governor feedback channels; the ordinary
four-channel observation is insufficient. Raw/filtered source must match the
training manifest. Session, source/frame, freshness, skew, cadence and replay
checks fail closed. The portable actor uses only Python/stdlib plus the SDK and
checks its inference source hashes. It does not apply a second governor. This
does not add a portal submission path or authorize a hardware runner. Recorded
shadow testing, timing measurements and bounded physical acceptance remain
separate work.

## Headless Google Colab CLI

Use Google's official [`google-colab-cli`](https://github.com/googlecolab/google-colab-cli)
from a local terminal. The commands below target **0.7.4**, verified on
2026-10-17 against the published package's help and source. It requires Python
3.12+ on the local CLI host (Linux or macOS); the separate training environment
below uses Python 3.11.7. [Published release](https://pypi.org/project/google-colab-cli/0.7.4/).

This is a ready-to-run recipe **after fitting, reviewing and exporting the model**
and preparing the four inputs above. The rejected recordings are not training
inputs. Local package/help checks and the PPO pipeline have been tested; **no
Colab login, runtime allocation or cloud training has been tested**. A short
execution check still provides no evidence of model fidelity or policy quality.

### Install locally and authorize once

From the repository root, use a separate CLI environment:

```sh
uv venv --python 3.12 runs/colab-cli-venv
uv pip install --python runs/colab-cli-venv/bin/python google-colab-cli==0.7.4
colab() { runs/colab-cli-venv/bin/colab --auth oauth2 "$@"; }
colab --help
colab version
```

Version 0.7.4's installed help and `cli.py` default to `oauth2`; the README's
`adc` default is stale. The explicit flag avoids that ambiguity. On the first
authenticated command, the CLI prints a Google authorization URL. **You open
that URL, approve access, and paste the authorization code into your terminal.**
It caches credentials locally for later commands. This human consent step uses
a browser; uploading and running training do not require a notebook browser.
The bundled OAuth client supports this flow, so creating a client configuration
or setting up ADC is unnecessary for this recipe. This local Colab API login is
separate from granting cloud-service credentials inside a VM; the training
recipe does not need VM credentials or a Drive mount.
[Official authentication design](https://github.com/googlecolab/google-colab-cli/blob/main/docs/04_automation_and_utility.md),
[CLI default](https://github.com/googlecolab/google-colab-cli/blob/main/src/colab_cli/cli.py).

### Package inputs, allocate CPU and upload

These archives contain selected source and reviewed inputs. Do not add keys,
environment files, CLI credential caches, or unrelated raw recordings. A private
repository does not need to become public or be cloned using a token in Colab.
`README.md` is required by the Python build metadata.

```sh
python -m zipfile -c cartpole-source.zip pyproject.toml README.md uv.lock src examples scripts
python -m zipfile -c cartpole-inputs.zip \
  runs/model.json runs/executor-parameters.json \
  runs/observation-config.json runs/prior-parameters.json

# This command authenticates if needed and allocates a real CPU runtime.
colab new -s cartpole-ppo
colab upload -s cartpole-ppo cartpole-source.zip /content/cartpole-source.zip
colab upload -s cartpole-ppo cartpole-inputs.zip /content/cartpole-inputs.zip
```

Omitting `--gpu` and `--tpu` requests CPU. The current PPO implementation uses
`device='cpu'`; requesting a GPU will not accelerate this implementation.
Keep the named session until its outputs have been downloaded. Upload and
download operate on files, so the result directory will also be zipped.
[Official command reference](https://github.com/googlecolab/google-colab-cli#command-index).

### Install the locked training environment

`exec` executes Python in the remote kernel. Its verified default timeout is
30 seconds; use an explicit timeout for installation and training. This setup
creates an isolated project environment, leaving Colab's notebook packages out
of the training process. The locked Linux Torch wheel can include CUDA
dependencies, but the policy still runs on CPU; do not switch Torch builds
between a checkpoint and its resume/evaluation.

```sh
colab exec -s cartpole-ppo --timeout 1800 <<'PY'
from pathlib import Path
import subprocess, sys, zipfile

project = Path('/content/cartpole-training')
project.mkdir(exist_ok=False)
with zipfile.ZipFile('/content/cartpole-source.zip') as archive:
    archive.extractall(project)
with zipfile.ZipFile('/content/cartpole-inputs.zip') as archive:
    archive.extractall(project / 'inputs')
subprocess.run([sys.executable, '-m', 'pip', 'install', 'uv==0.8.11'], check=True)
subprocess.run(['uv', 'sync', '--locked', '--extra', 'rl', '--no-dev',
                '--python', '3.11.7'], cwd=project, check=True)
(project / 'training-python.txt').write_text('3.11.7\n')
(project / 'training-uv.txt').write_text('0.8.11\n')
subprocess.run(['sh', 'scripts/train-ppo', '--help'], cwd=project, check=True)
PY
```

### Train, evaluate and download

Save this small **local** launcher from the repository root. `exec -f` sends its
contents to Colab; the paths inside it are remote paths. It invokes the existing
training wrapper and preserves all admission checks and manifests.

```sh
cat > runs/colab-train.py <<'PY'
from pathlib import Path
import os, subprocess

project = Path('/content/cartpole-training')
run = os.environ['CARTPOLE_RUN']
resume = os.environ['CARTPOLE_RESUME']
command = ['sh', 'scripts/train-ppo', 'train',
    '--model', 'inputs/model.json',
    '--executor-parameters', 'inputs/executor-parameters.json',
    '--observation-config', 'inputs/observation-config.json',
    '--prior-parameters', 'inputs/prior-parameters.json',
    '--development-only', '--training-seeds', '11', '12', '13',
    '--seed', '20261017', '--seconds', '10', '--steps', '2048',
    '--n-steps', '1024', '--batch-size', '64', '--epochs', '10',
    '--checkpoint-every', '1024', '--output', f'runs/{run}']
if resume:
    command += ['--resume', f'runs/{resume}']
subprocess.run(command, cwd=project, check=True,
               env=dict(os.environ, UV_LOCKED='1', PYTHONUNBUFFERED='1'))
PY

colab exec -s cartpole-ppo --timeout 3600 -f runs/colab-train.py \
  --env CARTPOLE_RUN=ppo-001 --env CARTPOLE_RESUME=
colab exec -s cartpole-ppo --timeout 3600 <<'PY'
from pathlib import Path
import os, subprocess
project = Path('/content/cartpole-training')
subprocess.run(['sh', 'scripts/train-ppo', 'evaluate', 'runs/ppo-001',
    '--seeds', '1001', '1002', '1003', '1004', '1005', '1006',
    '--output', 'runs/ppo-001-heldout.json'], cwd=project, check=True,
    env=dict(os.environ, UV_LOCKED='1'))
PY
```

Run the following packaging/download block after training or resuming, and
before releasing the VM. It includes source, lockfile, input manifests,
checkpoints, portable actor and evaluation report, excluding the environment
and credentials. Only extract bundles you created or trust.

```sh
colab exec -s cartpole-ppo --timeout 300 <<'PY'
from pathlib import Path
import zipfile
project = Path('/content/cartpole-training')
selected = ['pyproject.toml', 'README.md', 'uv.lock', 'training-python.txt',
            'training-uv.txt', 'src', 'examples', 'scripts', 'inputs', 'runs']
with zipfile.ZipFile('/content/cartpole-results.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
    for name in selected:
        path = project / name
        for item in (sorted(path.rglob('*')) if path.is_dir() else [path]):
            if item.is_file() and '__pycache__' not in item.parts:
                archive.write(item, item.relative_to(project))
PY
colab download -s cartpole-ppo /content/cartpole-results.zip cartpole-results-001.zip
python -m zipfile -t cartpole-results-001.zip
# Run only after downloading and checking the bundle:
colab stop -s cartpole-ppo
```

The remote disk is temporary. Download periodic checkpoints during longer work
using the same packaging block; an interrupted run may only have complete
`runs/ppo-001/checkpoints/step-XXXXXXXXX` directories. Use a complete directory
as the resume input. If a terminal command disconnects or times out, inspect
the session before retrying; a client timeout is not proof that training stopped.

### Resume with the same source and versions

On the **same running session**, append another 2,048 steps into a new directory:

```sh
colab exec -s cartpole-ppo --timeout 3600 -f runs/colab-train.py \
  --env CARTPOLE_RUN=ppo-002 --env CARTPOLE_RESUME=ppo-001
```

If the VM was stopped, allocate a new CPU session, upload the downloaded bundle,
restore it, and recreate its exact environment before that resume command:

```sh
colab new -s cartpole-ppo
colab upload -s cartpole-ppo cartpole-results-001.zip /content/cartpole-results.zip
colab exec -s cartpole-ppo --timeout 1800 <<'PY'
from pathlib import Path
import subprocess, sys, zipfile
project = Path('/content/cartpole-training')
project.mkdir(exist_ok=False)
with zipfile.ZipFile('/content/cartpole-results.zip') as archive:
    archive.extractall(project)
uv_version = (project / 'training-uv.txt').read_text().strip()
python_version = (project / 'training-python.txt').read_text().strip()
subprocess.run([sys.executable, '-m', 'pip', 'install', f'uv=={uv_version}'], check=True)
subprocess.run(['uv', 'sync', '--locked', '--extra', 'rl', '--no-dev',
                '--python', python_version], cwd=project, check=True)
PY
colab exec -s cartpole-ppo --timeout 3600 -f runs/colab-train.py \
  --env CARTPOLE_RUN=ppo-002 --env CARTPOLE_RESUME=ppo-001
```

Resume and evaluation reject changed model/configuration, source, Python patch
version or recorded dependency versions. Do not regenerate `uv.lock`, upgrade
packages or silently bypass a mismatch. Reproduce the original environment or
start a new experiment. Cross-platform continuation is not promised. Preserve
the local launcher too; it fixes algorithm settings and seeds. For the resumed
policy, evaluate `runs/ppo-002` into a new report using a fresh disjoint set such
as `2001 2002 2003 2004 2005 2006` if the first evaluation informed further
training, then package/download again before `colab stop`.

### Optional browser notebook

[`notebooks/train_ppo_colab.ipynb`](../notebooks/train_ppo_colab.ipynb) remains an
optional interactive route using the same training CLI. It installs CPU Torch
separately, so its resolved versions can differ from this locked CLI recipe;
do not interchange checkpoints without satisfying the manifest version checks.
Neither route opens or controls the physical rig.

Official references: [SB3 PPO](https://stable-baselines3.readthedocs.io/en/master/modules/ppo.html),
[SB3 checkpoint format](https://stable-baselines3.readthedocs.io/en/master/guide/save_format.html),
[Gymnasium environment API](https://gymnasium.farama.org/api/env/).
