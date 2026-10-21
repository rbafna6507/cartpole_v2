# Filtered BAL foundation → combined swing-up and balance

**Both local pilots completed; the long Colab job is confirmed training.** This is a new projected-PPO experiment initialized from the supervised filtered BAL actor. Hardware balance observations belong to that frozen foundation; no learned hardware swing-up or acceptance of a new PPO checkpoint is claimed.

The reviewed adapter reuses `TrainingEnv`, `EquilibriumPPO`, `RetainedPPO`, the trace evaluator, and `check_candidate`. It does not alter runtime or simulator source. Existing robust-swing migration explicitly requires raw inputs, so it is not used for this filtered actor. The old Colab helper hardcodes a scratch trainer; the new bundle retains its setup, transport, locking, status and packaging and replaces only the selected research job.

## Frozen experiment

- Arms: `ppo` means **EquilibriumPPO**, including zero-output projection after each update. `retained` adds four actor-only fixed-anchor regression minibatches and another projection; it is not vanilla PPO or a trust-region guarantee.
- Optimizer seeds: 11, 23, 47; identical foundation actor, freshly seeded critics/optimizers/exploration, and equal budgets.
- Pilot: 102,400 steps per arm/seed; six-trial cloud matrix would total 614,400 steps. The two local seed-11 arms completed.
- Long: 1,024,000 steps per arm/seed; six trials total 6,144,000 steps. This is a separate fresh matched experiment, not a bitwise continuation of the pilot.
- Original finite 25-second objective and 50:50 hanging/upright starts; unchanged physical model, observer bandwidth 10, jerk 150, 100 Hz inputs, executor limits and 20 ms leases.
- Nominal acquisition training first. Upstream ±1° bias and 5/3 ms sensor/command delay scenarios are explicit evaluation options, not hidden training changes or identified uncertainty.
- Training poses 28000–28127; separate training-only anchor poses 28200–28203. Anchors contain 8,192 observed filtered input rows with frozen Gaussian-mean targets. No old raw demonstrations or ground-truth actor inputs.
- Development 98400–98403; reserved confirmation 98500–98507. Smoke uses 98600–98601. Reserved starts have not been run.

The initial model already achieved **4/4 hanging and 4/4 upright nominal development holds**, with mean hanging capture 7.08 s. All four hanging cases used rail braking, reaching about 0.2941 m; upright cases stayed within 72.9 mm without braking. This is simulated behavior of the supervised foundation, not evidence of new PPO learning. The existing long-horizon check also found that ±1° bias breaks the strict ±120 mm centering hold for both teacher and network while pole motion remains bounded.

`promotion-gate-addendum.json` supersedes the earlier low hanging-success threshold: preserve the initial balance/hold performance and show a concrete capture, dwell, centering, braking or matched stress improvement before claiming a reason for a larger budget. Initial checkpoint remains eligible. Any exploratory exception needs an explicit rationale after reviewing pilot results. Do not select on reserved confirmation starts, and do not treat parity as task qualification.

## Local pilot outcome

All nominal evaluations passed 4/4 hanging and 4/4 upright final holds with no faults. The initial supervised foundation already passed these cases.

| Checkpoint | Hanging capture mean | Minimum final dwell | Upright worst cart excursion | Hanging braking steps |
| --- | ---: | ---: | ---: | ---: |
| Foundation | 7.08 s | 16.81 s | 72.9 mm | 1,604 |
| Projected PPO, 51,200 | 5.35 s | 19.84 s | 88.2 mm | 945 |
| Projected PPO, 102,400 | 7.59 s | 15.44 s | 97.3 mm | 1,444 |
| Retained PPO, 51,200 | 6.93 s | 16.74 s | 73.2 mm | 1,559 |
| Retained PPO, 102,400 | 6.94 s | 16.69 s | 73.7 mm | 1,588 |

Projected PPO's midpoint improvement did not persist at the final checkpoint. Retention stayed close to the foundation. Every hanging case still uses rail braking near 0.29408 m. The selected local development checkpoint is projected PPO at 51,200 steps (`local-selection.json`), with its centering tradeoff retained. The longer matched experiment tests replication and duration effects; these results do not establish a monotonic benefit from more PPO updates or qualify hardware swing-up. `pilot-final-summary.json` binds all reports and verifies all 48 evaluation trace hashes and ten checkpoint hashes.

## Local jobs and validation

`local-launch-receipt.json` records exact commands and PIDs. Outputs/logs:

- `pilot-seed11-ppo/`, `pilot-seed11-ppo.log` — PID 28097.
- `pilot-seed11-retained/`, `pilot-seed11-retained.log` — PID 28098.

Both use one CPU thread. Based on observed training progress around 270 decisions/s, allow roughly 10–20 minutes for this parallel pair, including baseline and checkpoint evaluation; this is an estimate, not a cloud runtime promise. Prior analogous 102,400-step runs took 8–12 minutes each. A serial six-trial 1,024,000-step cloud matrix can take several hours and depends on the allocated VM.

Validation completed:

- 34 focused/adjacent tests, including filtered-only transfer, exact actor-only changes, seed isolation, evaluation provenance and training-mode restoration.
- Both arms completed real 128-step smoke training; weights changed, checkpoint reload passed, and SDK emission error was below 1e-6 m/s².
- Independent reviewer cleared final files with no Important/Critical issue.
- `colab-pilot-final` was extracted into an independent temporary checkout. All 145 input/source bindings passed; the extracted retained-PPO smoke ran using its own `src` and passed reload and SDK parity. Six-job command dispatch was checked offline with process execution stubbed.
- `colab-long-final` has the identical source archive; its recipe selects the long budget. The long bundle was launched by the campaign operator after reviewing midpoint pilot data; the pilot cloud bundle was not launched.

Superseded preparation attempts and the failed first evaluator-metadata smoke remain in this directory. Use only `colab-pilot-final` or `colab-long-final`, not `colab-pilot-bundle`.

## Headless Colab commands — long session launched

The active session is `filtered-bal-joint-long-20261021`, currently training the first projected-PPO seed-11 run. The original full-snapshot watcher exited on a kernel websocket connection loss after preserving its first snapshot. Its `colab-long-backups-01` archive remains intact. The separate HTTP-only checkpoint watcher below is now running as local PID 34652, launched by the campaign operator. The first checkpoint snapshot has downloaded and passed outer ZIP and inner checkpoint CRC/hash checks. `cloud-training-update.json` records the operator-reported status and the independently checked snapshot identity.

Run from `/Users/rbafna/projects/cartpole_v2`. **The long session has already been launched; do not repeat `start`.** The start command below is retained as a reproducibility record. The existing launcher refuses duplicate session names and does not retry ambiguous allocation outcomes. If a launch is uncertain, inspect status instead of repeating start.

```sh
.venv/bin/python examples/colab_training.py start evidence/policy-recovery-20261021/combined-next/colab-long-final --session filtered-bal-joint-long-20261021 --colab runs/colab-cli-venv/bin/colab

.venv/bin/python examples/colab_training.py status evidence/policy-recovery-20261021/combined-next/colab-long-final --session filtered-bal-joint-long-20261021 --colab runs/colab-cli-venv/bin/colab

.venv/bin/python examples/colab_training.py watch evidence/policy-recovery-20261021/combined-next/colab-long-final --session filtered-bal-joint-long-20261021 --colab runs/colab-cli-venv/bin/colab --output evidence/policy-recovery-20261021/combined-next/colab-long-backups-01 --poll-seconds 60 --max-seconds 43200
```

For a six-trial cloud **pilot**, substitute `colab-pilot-final`, `filtered-bal-joint-pilot-20261021`, and a new pilot backup directory. The cloud launch was a separate explicit decision recorded in `long-decision.json`; `cloud-launch-update.json` records the confirmed launch state. `watch` obtains hash/CRC-checked snapshots; an existing output path cannot be reused.

## Evaluation after training

For a chosen completed run, the adapter supports `evaluate --run RUN --step STEP --output NEW`. Default is 25-second development evaluation; `--stress` adds the pinned upstream bias/timing scenarios. `--numeric` runs the exported NumPy backend under `TrainingEnv` guards. The separate `final-emission-parity` path exercises normal SDK `NeuralPolicy.reset/act`.

Only after freezing a candidate, `--confirmation` uses reserved 60-second starts. Every evaluation records protocol hash, checkpoint hash, in-memory weight hash, experiment hash, adapter hash and trace hashes. New PPO checkpoints still require task evaluation and hardware qualification; none is automatic.

## HTTP-only checkpoint backups

The evidence-local `http_checkpoint_watch.py` replaces the failed websocket-dependent polling path for checkpoint preservation. It invokes only the pinned `google-colab-cli==0.7.4` **download** command through normal OAuth; each subprocess has a deadline of at most 45 seconds. It makes no kernel execution, allocation, start, restart or stop calls. The original full snapshot is preserved separately.

The operator has already launched PID 34652 with the 24-hour limit. Do not launch a duplicate. Commands below are for an explicit restart after the current watcher has exited:

```sh
.venv/bin/python evidence/policy-recovery-20261021/combined-next/http_checkpoint_watch.py --once --max-seconds 180

.venv/bin/python evidence/policy-recovery-20261021/combined-next/http_checkpoint_watch.py --poll-seconds 60 --max-seconds 86400
```

The default backup directory is `runs/colab-filtered-joint-long-20261021-checkpoints`, outside this evidence tree. The script supports resuming the same directory with matching session/protocol/CLI bindings and uses an exclusive local lock. It never replaces an existing checkpoint. The default duration is 12 hours; the explicit command above allows 24 hours for six serial long trials. Keep the local machine awake with network access.

Every complete poll verifies the frozen remote protocol, the atomic job-status snapshot, and the current plus completed whitelisted trial reports. It checks run identity, protocol identity and completed-report hashes, then retrieves every missing report-listed checkpoint and validates SHA-256 plus inner ZIP CRC before publishing it. `last-complete.json` records a successful full poll; `watch-status.json` and `events.jsonl` distinguish current health from an older successful backup. Per-checkpoint receipts and immutable metadata snapshots preserve provenance. Previously backed-up files are revalidated locally, not downloaded again.

Transport failures retry after 15 and 30 seconds, then stop on the third consecutive failed poll. A complete poll resets the count. A transient not-yet-written report is a transport failure; malformed reports, protocol mismatches, SHA/CRC mismatches and local conflicts are identified separately. Neither category can mark a new poll complete. Arbitrary exception text and CLI output are suppressed to keep credentials out of logs. The watcher stops after backing up a terminal job state, or at its configured duration; it does not control the remote job.

This backs up reports and resumable checkpoint ZIPs, not every evaluation trace or the complete remote filesystem. The earlier full snapshot remains the full-tree recovery artifact. Sixteen watcher tests plus nine adjacent driver tests pass, including a real hung-child timeout, checkpoint corruption, rollover and six-trial completion. Independent review found no Important/Critical issue. The campaign operator launched it; the implementation author made no remote calls. The first automatic poll succeeded with zero consecutive failures and verified checkpoints at steps 0 and 51,200. Its log is `runs/colab-filtered-joint-long-20261021-http-watch.log`; `http-watch-launch.json` records the launch.
