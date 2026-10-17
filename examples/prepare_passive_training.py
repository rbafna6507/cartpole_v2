#!/usr/bin/env python3
"""Prepare immutable Gym/PPO inputs from a frozen passive candidate; no rig access."""
import argparse
import json
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('freeze', 'executor-parameters', 'observation-config', 'assumptions', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        from cartpole_sdk.learning.model_experiment import read_json
        from cartpole_sdk.learning.passive_profile import build_passive_training_bundle
        executor, _ = read_json(args.executor_parameters)
        if executor.get('schema_version') == 1:
            executor = executor.get('parameters')
        observations, _ = read_json(args.observation_config)
        assumptions, _ = read_json(args.assumptions)
        result = build_passive_training_bundle(args.freeze, args.output,
            executor_parameters=executor, observation_config=observations, assumptions=assumptions)
        print(json.dumps(dict(output=str(args.output), status=result['status'], hardware_accepted=False,
                              bundle_sha256=result['content_sha256'])))
        return 0
    except (ValueError, OSError, ImportError) as exc:
        parser.exit(2, f'passive training profile: {exc}\n')


if __name__ == '__main__':
    raise SystemExit(main())
