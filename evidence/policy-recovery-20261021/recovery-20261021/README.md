# Colab recovery and operator policy comparison

The original Colab assignment disappeared on October 21 near 20:03 EDT. Its exact provider deletion reason is unknown. The detached supervisor left no continuously executing notebook cell; idle deletion is a documented exposure. See [diagnosis](diagnosis/diagnosis.md), including official sources and alternative explanations.

The recovery bundle resumes projected PPO seed 11 from step 460,800, preserving actor, critic, Adam moments and absolute counters. MuJoCo episode state and global random-generator state were not saved, so this is **not a bit-exact uninterrupted continuation**: the environment restarts within the same training seed family and the global RNG has an explicit restart seed. It finishes the original 1,024,000-step budget, then runs the remaining five original trials, without changing the frozen protocol. This leaves 5,683,200 training steps in the matrix. The recipe records the interruption boundary.

The new session is `filtered-bal-joint-recovery-20261021`. It uses an actual foreground notebook execution waiting for the real supervisor, while a detached local CLI process owns that execution. There is no synthetic keepalive. Colab remains interruptible; current free/zero-unit availability does not guarantee a full long-run lifetime. The local HTTP-only watcher preserves checkpoint/report snapshots in `runs/colab-filtered-joint-recovery-20261021-checkpoints`. Keep the Mac awake and connected for backup downloads and the CLI connection.

The original bundle, checkpoints, source pins, reports and successful hardware balance actor remain unchanged. Both setup and archive bindings were verified before launch. A source-extraction check verified 159 original/recovery bindings and loaded the full checkpoint with 13 populated optimizer parameter states. Seven new tests and 50 adjacent tests passed. The full repository suite passed 2,030 tests, 8 skipped, 460 subtests.

## Read status without interrupting the training cell

From the Mac repository:

```bash
cd ~/projects/cartpole_v2
.venv/bin/python evidence/policy-recovery-20261021/recovery-20261021/status.py
```

This reads job/report/progress files over HTTP. A recorded `training` state alone does not prove the process is alive; use advancing `latest_progress` and recent successful downloads. The old `./scripts/colab-training status` performs a kernel execution and can queue behind this genuine long-running training cell; use the HTTP command above for this session. Do not rerun allocation/start to check status.

Watcher receipts: `watch-launch.json`, and its output directory's `watch-status.json`/`last-complete.json`. `launch.json` binds the bundle, session and local foreground owner. A client failure is not permission to relaunch blindly; inspect job files and session state first. The watcher stops after three consecutive failures or 24 hours. Only after its old process exits, restart the same bound output with:

```bash
.venv/bin/python evidence/policy-recovery-20261021/recovery-20261021/watch.py --max-seconds 86400
```

## Hardware trials

Both recovered actors are staged additively on the Jetson. No motion, serial access, firmware upload, calibration or parameter changes were made. Start with the 102,400-step actor: its nominal swing-up is faster and its upright centering is slightly better than the 460,800-step actor. Full results and exact commands are in [policy/README.md](policy/README.md).

The current console admits only centered, nearly stationary **upright** starts. These commands can compare the recovered network's balance on hardware; they do not start learned swing-up from hanging. All hanging simulation tests used native rail braking. Neither recovered PPO actor has yet been run or qualified on hardware, and the previously successful balance actor remains separately selectable.
