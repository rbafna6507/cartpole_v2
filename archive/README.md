# Runnable baselines and historical data

| Path | Purpose |
|---|---|
| `good_balancing_jetson/` | Minimal working console, saved tuning, one firmware tree, uv packaging, and relevant tests |
| `vision3/` | Existing vision3 algorithm and dashboard, with uv packaging; future vision work must use a separate directory |
| `vision2/` | Unmodified earlier reference, retained at the owner's request |
| `vision-tunnel.sh` | Foreground local SSH forward from Mac port 3095 to Jetson port 3090 |
| `jetson_known_hosts` | Previously verified public SSH host key; contains no private key or credential |
| `uncommitted-evidence/` | Unique measurements which were ignored by Git; local only, not needed for running the rig |
| `tests/` | Tunnel invocation tests; no real SSH connection |

## Git preservation, not duplicate originals

The baseline commit is `1d48532c4987e6e12b40ddeb2a78931ff701c3e0`.
Every inventoried tracked file matched its committed Git blob before cleanup.
The local `origin/main` reference also pointed to that commit; no remote fetch
or remote availability check was performed.

Redundant firmware trees, repository snapshots, characterization scripts, and
previous planning documents were removed from the working tree. There is no
`originals/` or `previous-v2-planning/` directory: Git already retains that source.
For example:

```bash
git show 1d48532:docs/roadmap.md
git show 1d48532:good_balancing_jetson/local_repository_snapshot/cartpole.py
```

To recover a whole old directory without overwriting the current tree, extract
it from `git archive 1d48532 PATH` into a separate destination.

Git did **not** contain all local data: the inventory found 843 ignored files.
The cleanup retained 353 unique uncommitted files (536.74 MiB) from the old good
balancing bundle, removed 340 byte-identical duplicates, and discarded generated
caches/build outputs. Vision3's existing recordings remain under `vision3/runs/`.
The old derived replay overlay was discarded; its source data remains recoverable.

These retained recordings are ignored, not backed up by a Git clone. Their exact
paths, checksums and duplicate mappings are in
[`uncommitted-files.json`](../evidence/phase0/uncommitted-files.json). The complete
pre-cleanup inventory is [`source-inventory.json`](../evidence/phase0/source-inventory.json).

## Tunnel

```bash
./archive/vision-tunnel.sh
```

The default target is `jetson`, using your existing SSH configuration and known
hosts, just like `ssh jetson`. This follows your configured/DNS-resolved route
instead of a hardcoded historical IPv6 address. Connection attempts time out
after 10 seconds. The initial message is not confirmation that SSH has connected.
Keep host-key verification enabled and verify a new host key independently before
updating it. Do not copy a private SSH key here.

```bash
JETSON_KNOWN_HOSTS="$HOME/.ssh/known_hosts" ./archive/vision-tunnel.sh rbafna@jetson
LOCAL_PORT=4095 ./archive/vision-tunnel.sh
```

`JETSON_KNOWN_HOSTS` explicitly overrides the configured host-key file; omit it
to honor your SSH configuration. The bundled `jetson_known_hosts` file contains
historical IPv6 entries and is available for explicit legacy connections.
The second command opens the viewer on port 4095 if 3095 is busy. `REMOTE_PORT` defaults to 3090.
Forwarding failure is an error; the script never kills another tunnel or server.
Ctrl-C closes the foreground tunnel. The website stays bound to loopback.

For a lightweight transfer to the Jetson, copy the two runnable package directories
without `.venv`, `__pycache__`, `*.egg-info`, `runs`, or `logs`. Preserve the
`vision3/console` relative symlink if you want to run its integration tests.
