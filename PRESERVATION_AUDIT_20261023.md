# Preservation audit — October 23, 2026

This record covers the initial read-only preservation phase, before the user separately authorized the October 23 operator release changes described in SYSTEM_README.md section 24. It accompanies [SYSTEM_README.md](SYSTEM_README.md) and [SYSTEM_REFERENCE.md](SYSTEM_REFERENCE.md). It preserves the system before further development. No firmware, deployment source, settings, calibration, service, serial session, or physical rig state was changed during the audit. New documentation was written, existing source changes were committed unchanged, and recovery archives were copied/uploaded.

## Source and conversation provenance

- Local repository: `/Users/rbafna/projects/cartpole_v2` (the user’s `/projects/cartpole_v2` shorthand).
- GitHub: [rbafna6507/cartpole_v2](https://github.com/rbafna6507/cartpole_v2), a public repository.
- Working branch: `codex/live-rig-platform`; GitHub’s default branch remains `main`.
- Initial HEAD: `cbd833b`, 33 commits ahead of the remote tracking branch. All 33 were pushed successfully.
- Preserved pre-existing viewer work: commit `d558aa2`, pushed successfully. The five source/test files were committed without editing their contents.
- Raw untracked Colab evidence remains outside the source commit and is preserved in the approved release archive. This is why untracked evidence can remain visible in `git status` even after all source changes are pushed.
- Historical chat: **Plan Cartpole software v2**, ID `01a136d1-fae8-7b92-ba51-dad61741114c`. The local conversation record contained 255 user messages, 66 final answers and 864 assistant commentary messages, plus tool evidence and compaction records. The README synthesizes the conversation’s decisions/results and checks them against actual code and retained evidence; historical statements are not treated as a current hardware interrogation.
- The private conversation export is not included in the public source commit or backup assets.

## Jetson deployment identity

`/home/rbafna/cartpole-v2-live` is a deployment tree, not a Git checkout. Its `current` directory is an old directory rather than a symlink to the newest release. The latest inspected release is `releases/id-20261021-policy-swingup`.

The tree contains these releases:

```text
platform-20261013
platform-20261014-cart-switches
platform-20261014-encoder
platform-20261014-parameters
platform-20261015-rehome
platform-20261015-v5-jerk600
platform-20261015-v6-tunable
id-20261020
id-20261021-policy-console
id-20261021-policy-rail1mm
id-20261021-policy-swingup
```

It also contains staging snapshots for operator identification, camera-zero collection, Python feedback, RL shadow, and system identification, plus loader/build/evidence files. Exact bytes are preserved rather than overlaid onto current development source.

The deployment-source archive contains **3,203 regular files / 47,861,827 uncompressed bytes**. Every file matched the SHA-256 inventory collected on the Jetson: **zero mismatches**. The source-only inventory excludes virtual environments, caches, `runs`, and symlink files; the separate full live-tree archive includes run data. No serial query was made, so neither an archived image nor a README proves the currently flashed MCU identity or RAM/EEPROM state.

## Latest release compared with local source

There are **168 identical, eight differing, and four release-only files** among the inventoried latest-release files. The live policy runtime and deployed actor JSON files match local source. Differences are retained, not automatically synchronized.

| Relative file | Result |
|---|---|
| `jetson-verification.json` | jetson_only |
| `verify-policy-swingup.py` | jetson_only |
| `deployment-files.json` | jetson_only |
| `POLICY-SWINGUP.md` | jetson_only |
| `src/cartpole_sdk/learning/robust_swing.py` | different |
| `src/cartpole_sdk/learning/colab_bundle.py` | different |
| `src/cartpole_sdk/learning/model_experiment.py` | different |
| `src/cartpole_sdk/learning/training_recipe.py` | different |
| `src/cartpole_sdk/learning/colab_remote.py` | different |
| `src/cartpole_sdk/sim/rig_gym_env.py` | different |
| `src/cartpole_sdk/sim/viewer.py` | different |
| `src/cartpole_sdk.egg-info/SOURCES.txt` | different |

The differing learning/simulation files represent local follow-up work after staging. The viewer difference was the interrupted final task’s uncommitted work, now preserved in `d558aa2`. `src/cartpole_sdk.egg-info/SOURCES.txt` is generated metadata. Release-only verification scripts/manifests remain in the exact deployment archive.

## Separate live camera service

The camera service works from `/home/rbafna/cartpole_v2`, an older Git checkout on `phase0-baseline` at `0111e6005118457cf5d0371680ebcc23ae8878b8`, with additional modified/untracked deployed files. Its user service is `/home/rbafna/.config/systemd/user/cartpole-vision.service`, and runtime settings come from `/home/rbafna/.config/cartpole-vision/runtime.env`.

The separate camera archive includes deployed source, service definition, runtime environment settings, and saved calibration; it excludes `.git`, virtual environments, caches, `runs`, and the historical `archive` subtree. The separate `jetson-vision-state-prefix-20261023.tar.gz` additionally preserves `~/.local/state/cartpole-vision`, including historical/current session logs. A first ordinary tar attempt detected growing files and was not used as the recovery asset. The replacement reads exactly each file’s size at open, records per-file timestamps/sizes/SHA-256 in `snapshot-manifest.json`, and verifies every archived prefix. It is intentionally a per-file prefix snapshot: the last JSONL line may be partial, and it is not a simultaneous freeze of all streams. The camera was left running, so this is a file-level capture, not a frozen process/RAM snapshot.

Among 97 source/script files, 74 match local and 23 differ, including generated package metadata. The meaningful camera-specific difference is the local arm-length gate in `src/cartpole_vision/app.py`, which is absent on the Jetson. Local code trusts the detected screw for cart-template selection only when the arm length is within 20% of the calibrated length. The deployed code trusts any detected pose. The tunnel wrapper has an older default hostname. No synchronization was performed.

| Camera-checkout file | Comparison |
|---|---|
| `scripts/vision-tunnel.sh` | different |
| `src/cartpole_sdk/identification/__init__.py` | different |
| `src/cartpole_sdk/sim/executor.py` | different |
| `src/cartpole_sdk/sim/viewer.py` | different |
| `src/cartpole_sdk/sim/backend.py` | different |
| `src/cartpole_sdk/sim/config.py` | different |
| `src/cartpole_sdk/policies/host.py` | different |
| `src/cartpole_sdk/policies/__init__.py` | different |
| `src/cartpole_sdk/contracts.py` | different |
| `src/cartpole_sdk/rig/protocol.py` | different |
| `src/cartpole_sdk/rig/client.py` | different |
| `src/cartpole_sdk/rig/console.py` | different |
| `src/cartpole_sdk/rig/parameters.py` | different |
| `src/cartpole_sdk/rig/policy.py` | different |
| `src/cartpole_sdk/control/reference.py` | different |
| `src/cartpole_sdk/control/motion.py` | different |
| `src/cartpole_sdk/control/parameters.py` | different |
| `src/cartpole_sdk.egg-info/entry_points.txt` | different |
| `src/cartpole_sdk.egg-info/requires.txt` | different |
| `src/cartpole_sdk.egg-info/SOURCES.txt` | different |
| `src/cartpole_sdk.egg-info/PKG-INFO` | different |
| `src/cartpole_sdk.egg-info/top_level.txt` | different |
| `src/cartpole_vision/app.py` | different |

## Archive scope and restoration

The user explicitly approved raw run/checkpoint backups and exact Jetson deployment archives, including vision settings/calibration, for upload to a **draft GitHub release**. Python environments and caches are excluded. The source branch and draft release serve different purposes: source is reviewable version control; release assets preserve bulky exact evidence and deployment snapshots.

`local-ignored-progress-20261023.tar.gz` contains local ignored runs/checkpoints and build/archival progress: 4,088 regular files and 6,732,267,752 uncompressed bytes. The complete archive was read successfully after creation. The four previously untracked Colab evidence files are captured separately in `local-untracked-evidence-20261023.tar.gz`, with each archived member hash checked against its local original. A final ignored-file sweep found ten additional training `progress.csv` files under evidence; these are preserved in `local-training-log-supplement-20261023.tar.gz`. The user separately approved uploading the camera session/calibration-state history; the verified prefix archive is included in the same draft release. Forty recovery checkpoints were separately checked against their SHA-256 receipts and ZIP CRCs. The latest complete receipt reaches projected seed 11 at 1,024,000 steps and retained seed 11 at 921,600 steps. This does not establish current cloud-job liveness or policy quality.

Large archives are uploaded in 512 MiB pieces with `.part001`, `.part002`, etc. Download **all** parts for that archive and concatenate them in numeric order:

```bash
cat local-ignored-progress-20261023.tar.gz.part[0-9][0-9][0-9] > local-ignored-progress-20261023.tar.gz
shasum -a 256 local-ignored-progress-20261023.tar.gz
mkdir recovered-cartpole-20261023
tar -xzf local-ignored-progress-20261023.tar.gz -C recovered-cartpole-20261023
```

Compare the assembled SHA with the table below before extracting. The deployment archive paths are relative to the live tree; the full archive has a `cartpole-v2-live/` prefix. Camera snapshot members include home-relative checkout/config paths. Always inspect `tar -tzf` and restore into a new directory. Do not extract onto a live deployment. Recreate Python environments from the applicable `pyproject.toml` and `uv.lock` rather than copying host-specific environments between macOS and Jetson.

## Fresh verification during the initial read-only audit

- Existing viewer test suite: **24 passed** (`tests/test_policy_viewer.py`, `tests/test_viewer.py`), with bytecode and pytest cache writing disabled.
- Learned viewer: headless hanging seed 98400, two simulated seconds, 200 decisions, horizon reached, no fault.
- Reference viewer: same start/seed, two simulated seconds, 2,000 decisions, horizon reached, no fault.
- No GUI rendering acceptance, full historical test-suite rerun, serial/hardware acceptance, firmware flash, cloud job inspection/restart, or new training was performed.
- Archive member reads and SHA-256 checks are recorded below. Source-byte preservation and pushed branch identity are checked after documentation installation.

## Verified recovery assets

All seven archives below were read and verified locally, and their uploaded assets were checked against GitHub SHA-256 digests. They are retained in the [draft preservation release](https://github.com/rbafna6507/cartpole_v2/releases/tag/untagged-3912b9bae148f286f11f). Draft assets require repository access; the release was not published. Full local archive copies and verification manifests are retained at `/Users/rbafna/projects/cartpole_v2/runs/preservation-20261023`.

| Archive | Compressed bytes | SHA-256 of assembled archive |
|---|---:|---|
| `jetson-releases-20261023.tar.gz` | 26085751 | `914ec04bfdfa5e432a11598ef7dc13f3d1e1e27853d5823634ba685b5a9d9074` |
| `jetson-vision-runtime-20261023.tar.gz` | 655155 | `79f1fb55c24a5982b81c2d685e2d9936feb3a5f1610c24b98faaddbc9c911ca2` |
| `local-ignored-progress-20261023.tar.gz` | 2524637490 | `bc3147fb15c185075c1698a6a5ce559265b7cd7ad886a538dcc0b916fcc0692f` |
| `local-untracked-evidence-20261023.tar.gz` | 2891244 | `0c6e424855b7336104536131c398cb7df605d3b23b35cd1e816aa44f27275573` |
| `jetson-vision-state-prefix-20261023.tar.gz` | 23976333 | `7eba451c6b76f450466d3507488bfd0e38988da57ea21cc6b4fd51491cfe513c` |
| `local-training-log-supplement-20261023.tar.gz` | 30910 | `06d187ef372bbba8f47895fdd8ae489fada7ffaa4cb5172ed816a14b2480ee6c` |
| `jetson-live-full-20261023.tar.gz` | 3573098291 | `c0d70575e74950b5879d281d68ca0c2ee938f213f521a239a0ea6eac7033b684` |

The full Jetson archive contains 5,194 inventoried entries (5,193 regular files and one symlink), totaling 19,654,703,784 regular-file bytes. Every entry matched the recorded path/size or symlink inventory, and all 3,203 source-file hashes matched the independent Jetson source inventory. The remaining run-data hashes were computed from the fully decoded archive; file sizes were checked against the remote inventory. This is not an independent second remote hash pass over every large log.

`restore-manifest.json` lists archive and upload-part hashes; `SHA256SUMS.txt` checks reconstructed archives. The full Jetson archive uses the same numbered-part reconstruction procedure as the local archive. Camera-state archive counts include the embedded manifest; its uncompressed-byte count reports the original captured files.

All 478 audited source files were byte-for-byte unchanged at the end of the initial read-only audit. The user then separately authorized operator/viewer/release implementation; those changes are documented in SYSTEM_README.md section 24. Source and documentation are pushed to `codex/live-rig-platform`; historical raw untracked evidence remains outside Git and is preserved in the release assets. Source and deployment differences are explicitly retained as described above.
