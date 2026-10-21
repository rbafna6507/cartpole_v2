#!/usr/bin/env python3
"""Record Python GC pauses around an unchanged campaign; never changes GC policy."""
import argparse
from collections import deque
import gc
import json
from pathlib import Path
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gc-output', type=Path, required=True)
    args, remaining = parser.parse_known_args()
    if args.gc_output.exists():
        parser.error('GC output must be new')
    events = deque(maxlen=10000)
    def event(phase, info):
        events.append((time.monotonic_ns(), phase, info['generation'], info.get('collected', 0), info.get('uncollectable', 0)))
    from cartpole_sdk.identification.campaign_cli import main as collect
    before = gc.get_stats()
    gc.callbacks.append(event)
    try:
        return collect(remaining)
    finally:
        gc.callbacks.remove(event)
        report = dict(schema='cartpole-gc-timing-probe-v1', thresholds=gc.get_threshold(),
            before=before, after=gc.get_stats(), columns=['host_monotonic_ns','phase','generation','collected','uncollectable'],
            events=list(events), bounded_capacity=events.maxlen,
            semantics='Callback timestamps include instrumentation overhead; GC configuration was unchanged.')
        args.gc_output.parent.mkdir(parents=True, exist_ok=True)
        with args.gc_output.open('x') as stream:
            json.dump(report, stream, indent=2)

if __name__ == '__main__':
    raise SystemExit(main())
