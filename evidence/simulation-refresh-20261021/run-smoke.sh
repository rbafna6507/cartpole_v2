#!/usr/bin/env bash
# Offline two-seed execution check; no rig or cloud access.
set -euo pipefail
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  echo 'Usage: run-smoke.sh NEW_OUTPUT_DIRECTORY'
  echo 'Run two 4096-step offline PPO checks and nominal evaluation; no hardware/cloud access.'
  exit 0
fi
repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd -P)
cd "$repo_dir"
output=${1:?Usage: run-smoke.sh NEW_OUTPUT_DIRECTORY}
mkdir -- "$output"
profile=training/profiles/rl-encoder-20261021
for suffix in 21 22; do
  uv run --locked --extra rl python examples/train_ppo.py train \
    --model "$profile/model.json" --executor-parameters "$profile/executor-parameters.json" \
    --observation-config "$profile/observation-config.json" --prior-parameters "$profile/prior-parameters.json" \
    --randomization "$profile/randomization.json" --development-only --seconds 5 \
    --seed "202610${suffix}" --steps 4096 --checkpoint-every 2048 --output "$output/ppo-seed$suffix"
  uv run --locked --extra rl python examples/train_ppo.py evaluate "$output/ppo-seed$suffix" \
    --seeds 81000 81001 81002 81003 --hold-seconds 5 --output "$output/ppo-seed$suffix-evaluation.json"
done
