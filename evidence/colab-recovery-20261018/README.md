# Colab runtime loss and checkpoint recovery — October 18, 2026

## What happened

All three original Colab assignments were absent from the server when inspected.
The CLI removed their local session records after discovering this; the local
`pruned` timestamps are detection times, not the actual termination times.

| Session | Created, America/Detroit | Last recorded observation | Missing detected |
| --- | --- | --- | --- |
| cartpole-encoder-001 | Oct17 18:38 | Training; independently observed10240 steps at18:41 | Oct18 09:03 |
| cartpole-vision-001 | Oct17 18:43 | Training at18:47 | Oct18 09:02 |
| cartpole-fused-001 | Oct17 18:45 | Launch acknowledged at18:47 | Oct18 10:35 |

The local histories contain no training traceback, completed result, or checkpoint
download. The user confirmed no downloads were saved elsewhere. We cannot tell
whether any run completed or crashed before its VM disappeared. Do not treat
these missing results as evidence about PPO convergence or blame parallelism.
The encoder was healthy at104 steps/s in the one early progress capture; at that
rate2,097,152 steps would take about5.6 hours before final evaluation.

[Sanitized history](original-job-history.json) preserves execution outputs and
relevant events, excluding credentials, endpoint tokens and submitted source.
No expired runtime was recreated under its old session name, and the old bundles
remain unchanged. Colab reports that VMs can be deleted when idle and have maximum
lifetimes; its limits vary. That makes runtime loss plausible, but does not
establish this incident's exact cause.
[Google's lifecycle/resource explanation](https://research.google.com/colaboratory/faq.html).

## Confirmed defects and repairs

1. The wrapper captured CLI stderr/stdout with `check=True`, then discarded them
   on a nonzero exit. The user saw a generic subprocess exception instead of
   `Session ... not found`. Both ordinary failures and timeouts now expose the
   original output. Remote Python success still requires a nonce-bound receipt.
2. Remote status repeated a stale `training` file without checking its supervisor.
   It now reports process liveness, last optimizer row, progress age and completed
   checkpoint directories; a dead supervisor is explicitly `interrupted`.
3. Checkpoints only on temporary VM storage cannot survive VM deletion. The new
   `watch` command downloads on new checkpoints and terminal states. Downloads
   stay `.part` until their remote SHA256/size and ZIP CRC checks pass. Earlier
   snapshots survive errors. It also saves local status/event history.
4. Transport downloads inherited an unbounded HTTP operation in CLI0.7.4. They
   now have a600-second subprocess timeout. The polling deadline is checked
   between bounded operations, so a call can extend the nominal deadline.

Watch never allocates, restarts, retries launches or bypasses provider lifetime
limits. It needs this laptop awake and online. Interrupting watch leaves remote
training running; restart it into a new local directory after checking status.
A missing runtime is not resurrected by polling. More frequent checkpointing is
now configurable; original defaults and the PPO learner/reward/sensors/governor
remain unchanged. The replacement baselines use20480-step checkpoint intervals.

## Live verification and results

See `pilot-summary.json`, `pilot-results.zip`, and `pilot-watch-events.jsonl` for
the bounded encoder recovery experiment. It uses20,480 decisions,25-second
randomized training episodes, the original optimizer seed/learning settings,
4096-step checkpoints and four separate evaluation seeds, each tested from
hanging and upright. The pilot completed with no execution failures and0/8 final five-second holds
(0/4 hanging,0/4 upright). Mean balanced fraction was0% hanging and1.29% upright.
All five periodic checkpoints and the final checkpoint were saved and verified
locally. This is an execution and recovery check, not qualification
or a fair comparison with a completed2M-step run. All checkpoint/archive receipts
are validated by the script below; no pickled model needs to be loaded to inspect
its hashes or evaluation summary.

All three replacement jobs were observed actively advancing training, with local
watchers running. The initial status snapshot predates their first20480-step
checkpoints; the completed pilot independently verified automatic downloads.
The three replacement long-run bundles, receipts and initial backup status are
listed in `replacement-jobs.json`. Their2M-step budgets and learning settings
match the original jobs; only backup/observability infrastructure and checkpoint
frequency changed. Live watcher logs and all subsequent snapshots remain under
`runs/`, which is intentionally ignored by Git. Frozen input bundles and the
completed recovery pilot are preserved with this evidence. New runtime expiration
is still possible; a local verified checkpoint makes its work recoverable.

## Commands

From the repository root, inspect the saved pilot without extracting it:

```sh
python3 evidence/colab-recovery-20261018/tools/inspect_download.py \
  evidence/colab-recovery-20261018/pilot-results.zip \
  --output runs/recovery-pilot-inspection.json
```

For another experiment, prepare a unique bundle/session, start it, and run watch:

```sh
./scripts/prepare-colab-training \
  --profile training/profiles/rl-encoder-20261017 \
  --steps 102400 --checkpoint-every 20480 \
  --output runs/colab-encoder-next
./scripts/colab-training start runs/colab-encoder-next --session cartpole-encoder-next
caffeinate -i ./scripts/colab-training watch runs/colab-encoder-next \
  --session cartpole-encoder-next --output runs/colab-encoder-next-backups
```

`caffeinate -i` is macOS-specific; it prevents idle sleep while watch runs, not
lid-closed/offline interruption. Use `watch` without it on other platforms.
Restore a downloaded ZIP into a fresh checkout, use its exact source, Python and
lockfile, and resume a complete manifest/checkpoint/actor through `train-ppo train
--resume ...` with the matching model and recipe. Resume retains optimizer and
weights but restarts episode scheduling; it is not bitwise uninterrupted training.
See [training/resume instructions](../../docs/rl-training.md).

## Software checks

Regression tests were observed failing before repairs. Independent review caught
both timeout-output loss and unbounded transport, now fixed. Focused checks:
24 passed. Full suite:1422 passed,7 skipped,456 subtests. Logs are in `verification/`.
No rig or firmware operations were performed during this investigation.
