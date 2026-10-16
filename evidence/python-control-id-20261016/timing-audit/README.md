# Saved timing analysis

`analyze_timing.py` reads completed `timing.json`, `report.json`, and optional JSONL recordings. It imports only Python's standard library. It does not import or execute the motion-capable diagnosis harness, connect to a rig, or change services, thread affinity, parameters, or controller source.

`analyze_timing_v2.py` preserves that behavior and adds half-open rolling one-second long-gap counts, active-interval stage statistics, and separate terminal stages. The first four results use version 1; subsequent results, including the CPU-placement repeats and logger-on/mirror-off addition, use version 2. Both source versions are retained for reproduction.

The output includes:

- Per-stage wall, caller-thread CPU, and wall-minus-CPU p50/p90/p95/p99/p99.9/max, in milliseconds.
- Board-clock observation gaps and exact sequence anchors, excluding a runner preflight observation that is not followed by `act`.
- Worst intervals partitioned into `observe`, `act`, `step`, `wait`, and gaps between instrumented calls.
- Where JSONL exists, command/action-record boundaries within `step`, and first-newer-frame receipt versus `wait` return.
- The final instrumented calls and saved failure events, exact input file hashes, run settings and thread affinity snapshots.

Detailed timing/identity fields ending in `_ns` are nanoseconds. Quantile blocks ending in `_ms` are milliseconds. Percentiles use linear interpolation between sorted samples. Small negative wall-minus-CPU values are retained because wall/CPU clock calls are not simultaneous.

“Off-thread-CPU dominated” means more than half the measured interval was not charged to the instrumented caller's CPU clock. It can include intended condition waits, blocking I/O, lock/GIL waits, or scheduling delays. It does not identify which occurred, and does not measure CPU consumption of reader/logger/mirror workers or other processes. A command-log timestamp is not a board actuation timestamp.

From the repository root:

```sh
.venv/bin/python evidence/python-control-id-20261016/timing-audit/analyze_timing.py \
  /path/to/completed/timing-run --output /tmp/fresh-timing-analysis.json
.venv/bin/python -m unittest discover \
  -s evidence/python-control-id-20261016/timing-audit -p 'test_*.py' -v
```

Multiple completed run directories are accepted. Without `--output`, JSON is written to stdout. `--top 4` limits detailed worst-event lists. Existing output files are never overwritten. Missing JSONL in intentional `--no-log` runs is represented explicitly; no receipt/write ordering is inferred from absent logs.

For slow transfers, the same source can run via standard input to Python on the host holding the logs, returning only the compact analysis. That remote operation only reads completed files. The exact source and output hashes are retained in `verification.json`.
