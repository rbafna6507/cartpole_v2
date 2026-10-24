#!/usr/bin/env python3
"""Offline realtime reset check using a saved actor and session; never opens serial."""
import argparse
import json
import resource
import shutil
import tempfile
import time
from pathlib import Path
from cartpole_sdk.recording import _session
from cartpole_sdk.portal.sandbox import Sandbox


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact', type=Path, required=True)
    parser.add_argument('--telemetry', type=Path, required=True)
    parser.add_argument('--numpy-root', type=Path, required=True)
    parser.add_argument('--cpu', type=int, default=5)
    args = parser.parse_args()
    session = None
    with args.telemetry.open() as stream:
        for line in stream:
            record = json.loads(line)
            if record.get('type') == 'session':
                session = _session(record['session'])
                break
    if session is None:
        raise RuntimeError('recorded session missing')
    with tempfile.TemporaryDirectory(prefix='cartpole-offline-actor-') as directory:
        shutil.copyfile(args.artifact, Path(directory) / 'actor.json')
        for attempt in range(3):
            began = time.monotonic()
            with Sandbox(directory, artifact_kind='actor-json', sensor_source='magnetic-step',
                         numpy_root=args.numpy_root, cpu_affinity=args.cpu, realtime=True,
                         wall_seconds=1, max_acceleration=25).launch() as child:
                child.reset(session)
                elapsed = time.monotonic() - began
                # Read the actual harness limit, not just the bwrap supervisor.
                parents = {}
                harnesses = set()
                for proc in Path('/proc').iterdir():
                    if not proc.name.isdigit():
                        continue
                    try:
                        status = dict(line.split(':', 1) for line in (proc/'status').read_text().splitlines() if ':' in line)
                        pid = int(proc.name)
                        parents[pid] = int(status['PPid'])
                        if b'/sdk/cartpole_sdk/portal/harness.py' in (proc/'cmdline').read_bytes() and status['Name'].strip().startswith('python'):
                            harnesses.add(pid)
                    except (OSError, ValueError, KeyError):
                        pass
                descendants = {child.process.pid}
                for _ in range(8):
                    descendants.update(pid for pid, parent in parents.items() if parent in descendants)
                actual = harnesses & descendants
                if len(actual) != 1:
                    raise RuntimeError('could not identify isolated harness')
                limits = resource.prlimit(actual.pop(), resource.RLIMIT_RTTIME)
                if limits != (500000, 500000):
                    raise RuntimeError('inference realtime ceiling not lowered')
                print(json.dumps({'attempt': attempt, 'reset_ack': True, 'startup_wall_s': elapsed,
                                  'inference_rttime_us': limits}), flush=True)


if __name__ == '__main__':
    main()
