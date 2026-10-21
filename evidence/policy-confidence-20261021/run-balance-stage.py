#!/usr/bin/env python3
"""Reproduce the frozen nominal balance screen; two one-thread CPU workers."""
import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = Path(__file__).resolve().parent
PROTOCOL = json.loads((EVIDENCE / 'protocol.json').read_text())
STAGE = PROTOCOL['initial_stage']
OUTPUT = ROOT / 'runs/policy-confidence-20261021/balance'

def run(arm, seed):
    name = f'{arm}-seed{seed}'
    output = OUTPUT / name
    if output.exists():
        raise FileExistsError(f'Preserving existing experiment: {output}')
    command = [str(ROOT / '.venv/bin/python'), '-u', 'examples/balance_learning.py', 'train',
        '--profile', PROTOCOL['profile'], '--output', str(output),
        '--initialization', arm, '--seed', str(seed), '--constraint', STAGE['constraint'],
        '--steps', str(STAGE['steps']), '--every', str(STAGE['steps']),
        '--seconds', str(STAGE['seconds']), '--evaluation-seconds', str(STAGE['evaluation_seconds']),
        '--evaluation-seeds', *map(str, STAGE['development_seeds']),
        '--learning-rate', str(STAGE['learning_rate']), '--policy-std', str(STAGE['policy_std'])]
    if arm == 'teacher':
        command += ['--gains', str(EVIDENCE / 'teacher-gains.json')]
    env = dict(os.environ, OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1')
    started = time.time()
    (OUTPUT / f'{name}-command.json').write_text(json.dumps(command, indent=2) + '\n')
    print(f'START {name}', flush=True)
    with (OUTPUT / f'{name}.log').open('w') as log:
        completed = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    result = {'name': name, 'returncode': completed.returncode, 'elapsed_seconds': time.time()-started}
    (OUTPUT / f'{name}-status.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)
    return result

def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    jobs = [(arm, seed) for seed in STAGE['optimizer_seeds'] for arm in STAGE['initializations']]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda pair: run(*pair), jobs))
    (OUTPUT / 'campaign-status.json').write_text(json.dumps(results, indent=2) + '\n')
    return int(any(result['returncode'] for result in results))

if __name__ == '__main__':
    sys.exit(main())
