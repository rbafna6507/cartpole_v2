"""Local recording and replay commands; no command connects to the rig."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

from .adapters import import_console, import_vision
from .contracts import ActionLimits, Channel, SOURCES
from .policies import AngularDampingPolicy
from .recording import read_recording, write_recording
from .replay import replay, write_trace


def inspect_recording(path):
    session, observations = read_recording(path)
    samples = tuple(s for o in observations for s in o.samples)
    quality = Counter(s.validity for s in samples)
    return {
        'session_id': session.session_id,
        'clock_id': session.clock_id,
        'cart': session.topology.cart,
        'joints': list(session.topology.joints),
        'observations': len(observations),
        'sources': sorted({s.source for s in samples}),
        'frames': sorted({s.frame_id for s in samples}),
        'validity_counts': {key: quality[key] for key in ('valid', 'invalid', 'unknown')},
        'first_available_ns': observations[0].available_ns if observations else None,
        'last_available_ns': observations[-1].available_ns if observations else None,
        'sequence_gaps': sum(b.sequence - a.sequence - 1 for a, b in zip(observations, observations[1:])),
    }


def _parser():
    parser = argparse.ArgumentParser(description='Cartpole SDK: local recordings and open-loop policy replay.')
    commands = parser.add_subparsers(dest='command', required=True)
    for command, description in (
        ('import-console', 'Import baseline console CSV into one recording per board-clock segment.'),
        ('import-vision', 'Import vision3 states JSONL from one calibration epoch.'),
    ):
        sub = commands.add_parser(command, help=description, description=description)
        sub.add_argument('input', type=Path)
        sub.add_argument('output', type=Path, help='New directory for console segments; new file for vision.')
        sub.add_argument('--session-id', required=True, help='Unique identity for this recording/run.')
        sub.add_argument('--frame-id', required=True, help='Explicit calibration/coordinate-frame identity.')
    inspect = commands.add_parser('inspect', help='Validate a recording and summarize sources and quality.')
    inspect.add_argument('recording', type=Path)
    run = commands.add_parser('replay', help='Run the illustrative angular-damping policy offline.')
    run.add_argument('recording', type=Path)
    run.add_argument('output', type=Path, help='New trace file; existing files are never overwritten.')
    run.add_argument('--source', choices=sorted(SOURCES), default='vision')
    run.add_argument('--joint', default='pole')
    run.add_argument('--frame-id', required=True)
    run.add_argument('--gain', type=float, default=0.05, help='Illustrative offline damping gain.')
    return parser


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == 'import-vision':
            session, observations = import_vision(args.input, args.session_id, args.frame_id)
            write_recording(args.output, session, observations)
            print(f'Imported {len(observations)} observations into {args.output}')
        elif args.command == 'import-console':
            # Parse all segments before publishing any files. Never reuse an output directory.
            segments = tuple(import_console(args.input, args.session_id, args.frame_id))
            args.output.mkdir()
            created = []
            try:
                for index, (session, observations) in enumerate(segments):
                    path = args.output / f'segment-{index:04d}.jsonl'
                    write_recording(path, session, observations)
                    created.append(path)
            except BaseException:
                for path in created:
                    path.unlink()
                args.output.rmdir()
                raise
            print(f'Imported {len(segments)} session segment(s) into {args.output}')
        elif args.command == 'inspect':
            print(json.dumps(inspect_recording(args.recording), indent=2, sort_keys=True))
        elif args.command == 'replay':
            session, observations = read_recording(args.recording)
            policy = AngularDampingPolicy(Channel(args.joint, 'angular_velocity', args.source, args.frame_id),
                                          gain=args.gain)
            # These limits belong only to the offline demonstration, not the rig.
            limits = ActionLimits(1.0, 20_000_000, 100_000_000)
            steps = replay(session, observations, policy, limits)
            write_trace(args.output, session, steps)
            count = sum(step.action is not None for step in steps)
            print(f'Offline replay: {len(steps)} observations, {count} requests, '
                  f'{len(steps)-count} without a request. Trace: {args.output}')
        return 0
    except (OSError, ValueError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
