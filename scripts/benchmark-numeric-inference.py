#!/usr/bin/env python3
"""Reproduce actor parity and warmed host latency without a device or Torch.

Run with the repository environment, e.g.:
  .venv/bin/python scripts/benchmark-numeric-inference.py --samples 10000

These host distributions are observations, not real-time guarantees. The
matrix-multiply comparison is benchmark-only; the selected backend avoids BLAS.
"""
import argparse
from contextlib import redirect_stdout
from datetime import datetime, timezone
import gc
from hashlib import sha256
import io
import json
import math
import os
from pathlib import Path
import platform
import random
import statistics
import sys
from time import perf_counter_ns


# This standalone process owns its environment. Set these before NumPy import,
# including for the benchmark-only BLAS comparison; the library changes none.
THREAD_VARIABLES = ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS',
                    'VECLIB_MAXIMUM_THREADS', 'BLIS_NUM_THREADS', 'NUMEXPR_NUM_THREADS')
ORIGINAL_THREAD_ENVIRONMENT = {name: os.environ.get(name) for name in THREAD_VARIABLES}
for name in THREAD_VARIABLES:
    os.environ[name] = '1'

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

import numpy as np

from cartpole_sdk.contracts import ValidationError
from cartpole_sdk.policies import neural
from cartpole_sdk.policies.numeric_backend import NumpyActorBackend
from cartpole_sdk.policies.rig_observation import rig_channels
from cartpole_sdk.recording import strict_json_loads


def encode_values(values):
    return dict(age_s=values[:7], state=values[7:14], valid=values[14:])


def synthetic_inputs(seed, random_cases):
    rng = random.Random(seed)
    result = [encode_values([value] * 21) for value in (0., 1., -1.)]
    for index in range(21):
        for value in (-1e6, -25., -1., -.02, .02, 1., 25., 1e6):
            values = [0.] * 21
            values[index] = value
            result.append(encode_values(values))
    for _ in range(random_cases):
        theta = rng.uniform(-math.pi, math.pi)
        result.append(dict(age_s=[rng.choice((-1., 0., .02, .15)) for _ in range(7)],
            state=[rng.uniform(-.31, .31), rng.uniform(-1.5, 1.5), math.sin(theta),
                   math.cos(theta), rng.uniform(-150., 150.), rng.uniform(-25., 25.),
                   rng.choice((-1., 0., 1.))], valid=[rng.choice((0, 1)) for _ in range(7)]))
    return result


def read_trace(path, actor_content_hash):
    """Extract raw, synchronous inputs matched by action observation sequence."""
    raw = path.read_bytes()
    states, actions = {}, []
    contract_ok = False
    for line in raw.decode().splitlines():
        row = strict_json_loads(line)
        if row['type'] == 'neural_preflight':
            contract_ok = (row['observation_contract']['angle_source'] == 'raw' and
                           row['actor_sha256'] == actor_content_hash)
        elif row['type'] == 'state':
            states[row['state']['unwrapped_tick']] = row['state']
        elif row['type'] == 'action_request':
            if not contract_ok:
                raise ValueError('trace must declare this actor and raw observation contract')
            request = row['request']
            state = states[request['observation_sequence']]
            if not state['flags'] & 1 or not state['flags'] & 4:
                raise ValueError('action state must have healthy encoder and homed position')
            features = dict(age_s=[0.] * 7, valid=[1] * 7,
                state=[state['x'], state['velocity'], math.sin(state['theta']),
                       math.cos(state['theta']), state['omega'], state['acceleration'],
                       state['brake_direction']])
            actions.append(dict(source=path.name, observation_sequence=request['observation_sequence'],
                encoded=features, recorded_acceleration_m_s2=request['acceleration_m_s2']))
    if not actions:
        raise ValueError('trace has no recorded actor action inputs')
    return dict(path=str(path), sha256=sha256(raw).hexdigest()), actions


class MatmulComparison:
    """Benchmark alternative with the same validation, packing and finite work."""
    def __init__(self, actor):
        neural.validate_actor(actor)
        self.order, self.scale = tuple(actor['feature_order']), actor['action_scale_m_s2']
        self.layers = tuple((np.array(layer['weights'], dtype=np.float64),
            np.array(layer['bias'], dtype=np.float64), layer['activation'] == 'tanh')
            for layer in actor['layers'])

    def predict_encoded(self, encoded):
        values = [float(value) for key in self.order for value in encoded[key]]
        if len(values) != 21 or not all(math.isfinite(value) for value in values):
            raise ValidationError('invalid actor features')
        values = np.asarray(values, dtype=np.float64)
        with np.errstate(over='ignore', invalid='ignore'):
            for weights, bias, tanh in self.layers:
                values = weights @ values + bias
                if not np.isfinite(values).all():
                    raise ValidationError('nonfinite actor inference')
                if tanh:
                    np.tanh(values, out=values)
        return max(-1., min(1., float(values[0]))) * self.scale


def distribution(samples):
    ordered = sorted(value / 1000. for value in samples)
    def quantile(q):
        position = (len(ordered) - 1) * q
        lower = int(position)
        upper = min(lower + 1, len(ordered) - 1)
        return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)
    return dict(count=len(ordered), min=ordered[0], mean=statistics.mean(ordered),
        p50=quantile(.5), p95=quantile(.95), p99=quantile(.99), p999=quantile(.999),
        max=ordered[-1])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--actor', type=Path, default=ROOT / 'training/candidates/balance-20261020/actor.json')
    parser.add_argument('--trace', type=Path, action='append', default=[])
    parser.add_argument('--replay', type=Path, action='append', default=[])
    parser.add_argument('--save-replay', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--samples', type=int, default=10000)
    parser.add_argument('--warmup', type=int, default=500)
    parser.add_argument('--random-cases', type=int, default=2000)
    parser.add_argument('--seed', type=int, default=20261021)
    args = parser.parse_args()
    if args.samples < 1 or args.warmup < 1 or args.random_cases < 0:
        parser.error('samples and warmup must be positive; random-cases must be nonnegative')
    raw = args.actor.read_bytes()
    if len(raw) > neural.MAX_BYTES:
        parser.error('actor exceeds numeric JSON size limit')
    actor = neural.validate_actor(strict_json_loads(raw.decode()))
    actor_file_hash = sha256(raw).hexdigest()
    numeric = NumpyActorBackend(actor)
    engines = dict(scalar=neural.NeuralPolicy(actor, channels=rig_channels(angle_source=actor['angle_source'])),
        **{'numpy-einsum': numeric, 'numpy-matmul-comparison': MatmulComparison(actor)})
    actions, sources = [], []
    if not args.trace and not args.replay:
        default_replay = ROOT / 'evidence/console-policy-20261021/numeric-replay-inputs.json'
        if default_replay.is_file():
            args.replay.append(default_replay)
    for path in args.trace:
        source, extracted = read_trace(path, actor['content_sha256'])
        sources.append(source)
        actions.extend(extracted)
    for path in args.replay:
        replay = strict_json_loads(path.read_text())
        if replay['actor_file_sha256'] != actor_file_hash:
            raise ValueError('replay actor file hash differs')
        sources.extend(replay['sources'])
        actions.extend(replay['actions'])
    replay = dict(schema='cartpole-numeric-inference-replay-v1', actor_file_sha256=actor_file_hash,
        reconstruction='raw control_observation: synchronized board ages zero, healthy/homed channels valid',
        sources=sources, actions=actions)
    synthetic = synthetic_inputs(args.seed, args.random_cases)
    cases = synthetic + [row['encoded'] for row in actions]
    max_error = {name: 0. for name in engines if name != 'scalar'}
    tolerance = actor['action_scale_m_s2'] * 2e-13
    for features in cases:
        expected = engines['scalar'].predict_encoded(features)
        for name in max_error:
            actual = engines[name].predict_encoded(features)
            error = abs(actual - expected)
            max_error[name] = max(max_error[name], error)
            if not math.isfinite(actual) or error > tolerance + abs(expected) * 2e-13:
                raise AssertionError(f'{name} scalar parity failed: {actual!r} vs {expected!r}')
    recorded_error = 0.
    for action in actions:
        error = abs(engines['scalar'].predict_encoded(action['encoded']) - action['recorded_acceleration_m_s2'])
        recorded_error = max(recorded_error, error)
        if error > 1e-12:
            raise AssertionError('reconstructed input differs from recorded scalar action')
    # Use real actions for timing when available. Warm every method, then
    # rotate engine order per sample to reduce drift/order effects.
    timed_cases = [row['encoded'] for row in actions] or synthetic
    for index in range(args.warmup):
        for engine in engines.values():
            engine.predict_encoded(timed_cases[index % len(timed_cases)])
    times = {name: [] for name in engines}
    names = list(engines)
    for index in range(args.samples):
        features = timed_cases[index % len(timed_cases)]
        offset = index % len(names)
        for name in names[offset:] + names[:offset]:
            started = perf_counter_ns()
            engines[name].predict_encoded(features)
            times[name].append(perf_counter_ns() - started)
    try:
        config = np.show_config(mode='dicts')
    except TypeError:  # Older NumPy builds expose only stdout configuration.
        stream = io.StringIO()
        with redirect_stdout(stream):
            np.show_config()
        config = stream.getvalue()
    result = dict(schema='cartpole-numeric-inference-benchmark-v1',
        measured_at_utc=datetime.now(timezone.utc).isoformat(),
        scope='offline warmed host observations; no hardware, scheduling or lease guarantee',
        actor=str(args.actor), actor_file_sha256=actor_file_hash, backend=numeric.provenance(),
        benchmark_source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        scalar_source_sha256=sha256(Path(neural.__file__).read_bytes()).hexdigest(),
        environment=dict(platform=platform.platform(), machine=platform.machine(),
            python=sys.version, numpy=np.__version__, numpy_config=config,
            original_thread_environment=ORIGINAL_THREAD_ENVIRONMENT,
            benchmark_thread_environment={name: os.environ[name] for name in THREAD_VARIABLES},
            gc_enabled=gc.isenabled()),
        parameters=dict(samples_per_engine=args.samples, warmup_per_engine=args.warmup,
            random_cases=args.random_cases, seed=args.seed, timed_inputs='real actions' if actions else 'synthetic'),
        parity=dict(synthetic_cases=len(synthetic), real_action_cases=len(actions),
            max_abs_error_m_s2=max_error['numpy-einsum'], alternative_max_abs_error_m_s2=max_error,
            max_recorded_scalar_error_m_s2=recorded_error, absolute_tolerance_m_s2=tolerance,
            relative_tolerance=2e-13, sources=sources),
        timings_us={name: distribution(values) for name, values in times.items()})
    if args.save_replay:
        args.save_replay.parent.mkdir(parents=True, exist_ok=True)
        args.save_replay.write_text(json.dumps(replay, indent=2, allow_nan=False) + '\n')
    output = json.dumps(result, indent=2, allow_nan=False) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output)
    else:
        print(output, end='')


if __name__ == '__main__':
    main()
