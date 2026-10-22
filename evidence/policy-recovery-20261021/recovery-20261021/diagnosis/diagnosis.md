# Disappeared Colab training session — 21 October 2026

The runtime assignment was lost; the precise provider deletion reason is **unknown**. The strongest actionable hypothesis is idle deletion: the launcher started training in a detached operating-system process, returned from its notebook cell, and later backups only downloaded files. This is a documented exposure, not proof that Colab applied that policy to this particular session.

## What the evidence establishes

All times below are America/Detroit (EDT).

- **18:29:37:** CLI history records allocation of a standard CPU runtime.
- **18:31:18:** The launch cell returned successfully with supervisor PID 3829. The frozen `remote.py:92–99` uses `subprocess.Popen(..., start_new_session=True)` and returns without waiting for training.
- **19:00:47:** Last completed kernel execution in local CLI history, a short status request. Later recorded operations are file transfers.
- **19:56:40:** Local file modification time for the latest preserved checkpoint, PPO seed 11 at **460,800 steps**. Its SHA-256 and ZIP CRC were independently rechecked successfully during diagnosis. Ten checkpoints are preserved; no trial had completed.
- **20:02:16:** Final successful full backup poll. This proves the files were reachable. It is not a live process check: `job-status.json` still contains the training state written at 18:31, and the incomplete report only lists saved checkpoint progress. Its `actual_steps=1024000` field is the configured total, not reached training progress.
- **20:03:19, 20:03:36, 20:04:08:** The CLI log records HTTP 404 responses from contents requests. The watcher stopped after three transport failures.
- **20:09:54:** CLI history records `session_terminated` with `reason=pruned`. Installed CLI source defines this as deleting local bookkeeping; it is not Google's shutdown cause.
- A subsequent read-only `colab usage` query returned **0.00 compute units, 0.00/hr, and zero active assignments**. Historical balance and plan entitlement are not established by that result.

Installed CLI is `google-colab-cli==0.7.4`. Its `exec` cleanup closes client channels without shutting down the kernel. Thus ordinary CLI exit is not itself evidence of a VM shutdown. The first websocket watcher failed much earlier while the replacement HTTP watcher kept succeeding; that earlier failure is separate from the later assignment loss.

## Interpretation and uncertainty

Colab documents variable idle and maximum-lifetime limits. Free notebooks may run for at most 12 hours; Pro+ supports continuous code execution up to 24 hours with sufficient units. These ceilings do not promise a minimum runtime. Zero balance now cannot prove exhaustion caused this incident. [Official FAQ](https://research.google.com/colaboratory/faq.html#resource-limits)

The Colab team specifically explains that Pro+ background protection requires an active or unacknowledged notebook execution. Once execution finishes, idle policy applies. A detached training process does not itself show that such an execution remains active. The same team also distinguishes runtimes deleted for becoming unhealthy, potentially from OOM or application failures. These statements support alternatives; they are not logs for this account. [Colab team explanation](https://github.com/googlecolab/colabtools/issues/5950)

A routine training exception is not documented in the preserved evidence. The supervisor normally catches subprocess errors and writes a failed status, which by itself would not remove the VM assignment. OOM, host failure, resource reclamation, or service policy remain possible because no terminal training log, exit status, or resource telemetry survived. Only provider-side deletion logs could identify the exact cause; Colab's Help → Send feedback is the documented route to request investigation. No feedback was sent.

## Recovery pattern and scoped improvements

Run the **real training supervisor synchronously inside a notebook/kernel execution**, using a blocking `job()` or `subprocess.run`, with a client timeout sized for the workload. A detached local CLI process can own that real execution. Keep the separate HTTP checkpoint watcher and resume only from an independently verified checkpoint with explicit continuation provenance. This is normal workload execution, not synthetic activity or an idle-timeout bypass. It still cannot guarantee an interruptible Colab VM's lifetime. [Official CLI session design](https://github.com/googlecolab/google-colab-cli/blob/main/docs/01_session_management.md)

Small robustness changes worth choosing separately:

1. Preserve incremental training logs, process exit status, and bounded resource telemetry alongside checkpoints.
2. Keep safe HTTP status and server-assignment observations distinct from generic transport failures; do not log credentials.
3. Record genuine progress timestamps. A static launch-time `training` status and a later download time do not prove continued execution.
4. If dependable long jobs are required, evaluate paid or dedicated compute with appropriate runtime guarantees; no allocation or purchase was made in this diagnosis.

`diagnosis.json` contains exact source/evidence bindings, sanitized event history, and checkpoint verification. This investigation made no cloud job execution, allocation, stop, CLI upgrade, hardware access, or production code change.
