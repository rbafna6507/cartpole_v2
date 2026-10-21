# Oct21 balance operator trace audit

The latest failure is the explicit host raw-demand ceiling, not an invalid action type, cadence failure, firmware fault, or the rig profile's rail/speed guard. The deterministic actor returns **Acceleration(+3.120775815247386 m/s²)** for board sequence **494738103**. The invocation selects **3.0 m/s²**, so the shared runner refuses the fourth action before sending it. Its hardcoded word “commissioning” does not describe the selected profile. `guard_profile=rig`, duration 55 s, and ceiling 3.0 are all confirmed by the log.

| Local start time, America/Detroit | Log timestamp identity | Actions sent | Outcome |
|---|---|---:|---|
| Oct21 10:20:40.889 | 1792592440889111951 / 2139398878 | 0 | Pre-ARM startup refusal: raw angle 0.07669904 rad (4.3945°) exceeds unchanged 0.07-rad startup bound. |
| Oct21 10:22:29.764 | 1792592549763586908 / 4249800223 | 0 | Pre-ARM startup refusal: raw angle 3.07103 rad, hanging. Rig profile retains upright admission for this balance-only actor. |
| Oct21 10:23:06.345 | 1792592586345230640 / 2520874797 | 3 | Fourth demand +3.120775815247386 exceeds selected 3.0. |

The latest accepted demands are +0.00680486544568145, −0.20258204470481356, and −0.4871880577461253 m/s² on observation sequences 494738073/83/93. Offline replay reproduces all three within 1.4e−15 m/s². The rejected fourth observation is 10 ms after the third, at counted x=0 m, commanded v=−0.0051809 m/s, raw angle=0.0398835 rad (2.2852°), filtered rate=0.7718396 rad/s, and governor acceleration=−0.4871881 m/s². No conclusion about physical cause of this short angle movement is supported by these few samples.

Latest ARM ACK→failure is **32.763768 ms**; ARM ACK→first STOP ACK is **33.440554 ms**. The first action anchor→refused observation is 30 ms of board time. Failure→first STOP ACK is **0.676786 ms**. All three Oct21 attempts have four STOP acknowledgments, no STOP failure, and final disabled/healthy/fault-zero telemetry. The latest has no firmware misses or dropped-state counter increment; its JSONL logger reports zero records dropped. Final counted x is −0.0000375 m, commanded velocity/acceleration zero, flags205/mode0/fault0. STOP confirmation is not independent physical-rest proof.

These records provide **no sustained learned hardware hold**. Requested55 s is not achieved55 s. The only earlier armed record in the archive (Oct20 21:05:06) has seven accepted actions and about72.8 ms ARM ACK→STOP ACK; it crosses the former 1-rad/s commissioning rate envelope at −1.345348 rad/s. The first Oct20 record has no ARM or policy_start; its logged bw8 differs from the actor's bw10, consistent with admission refusal, but no failure reason is recorded and that cause is not asserted as proven.

The mathematical ceiling needed to admit this one known rejected demand is at least3.120775815247386; e.g.3.2 would pass this particular observation, without any guarantee about the next. To permit the actor's complete declared action space, use the existing full invocation with **`--guard-profile rig --duration 55 --max-acceleration 25`**. This explicitly increases the host refusal ceiling; it does not prove balance performance or change native acceleration/jerk/rail/speed/switch/lease authority. The validated actor action scale and recorded amax_s/amax_b are all25. The balance-only actor still needs a centered, quiet upright start, saved reference330, and matching live parameters. No command was executed by this audit.

Two narrow diagnostic/display changes are possible entirely in `learning/balance_hardware.py`, which is outside the actor's18 pinned runtime files: inspect the returned intent against the already selected ceiling and include its exact value in the existing host-policy failure path; and supply the existing EncoderPublisher in CLI Rig construction, with an opt-out. Neither needs altered actor weights, compatibility pins, shared runner logic, or implicit clipping.

Reproduction (local CPU only; creates no Rig or transport), from the repository
root with its SDK environment installed:

```sh
replay_dir=$(mktemp -d)
archive=evidence/camera-id-20261021/live/balance-operator-20261021.tar.gz
mkdir "$replay_dir/extracted"
tar -xzf "$archive" -C "$replay_dir/extracted"
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  evidence/camera-id-20261021/operator-policy/analyze.py \
  --logs-dir "$replay_dir/extracted" \
  --archive "$archive" \
  --actor training/candidates/balance-20261020/actor.json \
  --output "$replay_dir/reproduced-summary.json"
```

All input and output locations are CLI arguments. `--logs-dir` accepts either
the extraction root or its `runs/my-balance-01` subdirectory; the analyzer reads
`rig-*.jsonl` files recursively. `--archive` supplies the original archive for
hash provenance; the analyzer does not extract it. The output must be a new
path, so the committed original `summary.json` cannot be silently overwritten.

The last run must reproduce `failed_prediction.demand_m_s2` as
`3.120775815247386`, observation sequence 494738103, and three accepted action
requests. Replay asserts every recorded action agrees with the unchanged actor
to within 1e−12 m/s² and verifies all actor/runtime pins before inference.
`summary.json` preserves the original individual input hashes, states, requests,
failure/STOP timings, and replay results. Rerun outputs record their own analyzer
source hash and current unpinned wrapper source hash. Output file/actor/archive
paths vary with checkout and extraction location; those paths are not numerical
results. The original wrapper hash belongs to the deployed pre-fix source;
wrapper-only diagnostic changes preserve the numeric inference.

The adjacent `full-suite.log`, `tdd-red.log`, `verification.json`, and
`fixed-wrapper-replay.json` are byte-for-byte copies of the Oct21 launcher-fix
verification artifacts originally produced in the temporary offline audit
workspace. They are historical evidence: the verification manifest's
`analyze.py` and `report.md` hashes refer to the original pre-CLI copies, not to
these portable revisions. Its copied log/replay/summary hashes retain their
original meaning. The red log contains the expected pre-fix test failures;
the full-suite log records 1787 passed, 7 skipped, 456 subtests passed. The fixed
wrapper replay preserves the three accepted predictions and records the precise
fourth-action refusal. No SDK source, actor weights, or runtime pins were changed
while making this evidence portable.

Archive SHA256: `012c406f0762bfa67a2a7b4c4896f82f4ef43f31198f480e7d7ab3d62d6a1ad5`.

Actor file SHA256: `b6d1179873eadbfebe0798e7cc39c17f05cc1bf7d9983733550e26e5681e6f08`.

Actor content SHA256: `ada6784ce953ecb90ae598f1c884b6f6a435e91c7c0b9b1396e140e24996f223`.

Deployed wrapper SHA256: `de7dca751a106b25c0f5a03adf420433d0fe9021eefcce130b775e4a73d7d904`.
