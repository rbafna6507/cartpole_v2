#!/usr/bin/env python3
"""Train/resume/evaluate a model-bound PPO actor offline; no rig access."""
import argparse
import json
from pathlib import Path

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    train = commands.add_parser('train', help='Train PPO and save resumable checkpoint plus numeric SDK actor.')
    for name in ('model', 'executor-parameters', 'observation-config', 'prior-parameters', 'output'):
        train.add_argument('--' + name, type=Path, required=True)
    train.add_argument('--development-only', action='store_true', help='Conspicuously admit unqualified simulation work; never accepts a rejected fit.')
    train.add_argument('--training-seeds', type=int, nargs='+', required=True)
    train.add_argument('--seed', type=int, required=True)
    train.add_argument('--steps', type=int, required=True)
    train.add_argument('--seconds', type=float)
    train.add_argument('--n-steps', type=int, default=1024)
    train.add_argument('--batch-size', type=int, default=64)
    train.add_argument('--epochs', type=int, default=10)
    train.add_argument('--checkpoint-every', type=int, default=10000)
    train.add_argument('--resume', type=Path)
    evaluate = commands.add_parser('evaluate', help='Frozen deterministic evaluation on disjoint seeds.')
    evaluate.add_argument('run', type=Path)
    evaluate.add_argument('--seeds', type=int, nargs='+', required=True)
    evaluate.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        from cartpole_sdk.learning.model_experiment import build_experiment, read_json
        from cartpole_sdk.learning.ppo import train_ppo, evaluate_ppo, _write_new
        if args.command == 'train':
            executor, _ = read_json(args.executor_parameters)
            if executor.get('schema_version') == 1:
                executor = executor.get('parameters')  # Complete recorded Rig profile; no defaults filled.
            observations, _ = read_json(args.observation_config)
            prior, _ = read_json(args.prior_parameters)
            experiment = build_experiment(args.model, executor_parameters=executor,
                observation_config=observations, prior_parameters=prior,
                development_only=args.development_only, seconds=args.seconds)
            print('DEVELOPMENT_ONLY: PPO in simulation; model scope does not qualify global swing-up or hardware.', flush=True)
            manifest = train_ppo(experiment, args.output, training_seeds=tuple(args.training_seeds),
                seed=args.seed, total_timesteps=args.steps, n_steps=args.n_steps,
                batch_size=args.batch_size, n_epochs=args.epochs,
                checkpoint_every=args.checkpoint_every, resume=args.resume)
            print(json.dumps(dict(output=str(args.output), algorithm='PPO',
                timesteps_completed=manifest['timesteps_completed'], hardware_accepted=False)))
        else:
            if args.output.exists():
                raise FileExistsError(args.output)
            report = evaluate_ppo(args.run, seeds=tuple(args.seeds))
            _write_new(args.output, report)
            print(json.dumps(dict(output=str(args.output), episodes=report['episodes_count'],
                successes=report['successes'], mean_score=report['mean_score'], hardware_accepted=False)))
        return 0
    except (ValueError, OSError, ImportError) as exc:
        parser.exit(2, f'cartpole PPO: {exc}\n')


if __name__ == '__main__':
    raise SystemExit(main())
