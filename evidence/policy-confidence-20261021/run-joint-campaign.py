#!/usr/bin/env python3
"""Run the frozen two-arm joint-task screen with two one-thread workers."""
import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
PROTOCOL=json.loads((HERE/'joint-protocol.json').read_text())
OUT=ROOT/'runs/policy-confidence-20261021/joint'

def run(job):
    arm,seed=job;name=f'{arm}-seed{seed}';output=OUT/name
    if output.exists():raise FileExistsError(output)
    cmd=[str(ROOT/'.venv/bin/python'),'-u',str(HERE/'run-joint-stage.py'),'train','--arm',arm,'--seed',str(seed),'--output',str(output)]
    (OUT/f'{name}-command.json').write_text(json.dumps(cmd,indent=2)+'\n')
    env=dict(os.environ,OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1')
    began=time.time();print('START '+name,flush=True)
    with (OUT/f'{name}.log').open('w') as log: result=subprocess.run(cmd,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
    report=dict(name=name,returncode=result.returncode,elapsed_seconds=time.time()-began)
    (OUT/f'{name}-status.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
    return report

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    jobs=[(arm,seed) for seed in PROTOCOL['optimizer_seeds'] for arm in PROTOCOL['arms']]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(run,jobs))
    (OUT/'campaign-status.json').write_text(json.dumps(results,indent=2)+'\n')
    return int(any(row['returncode'] for row in results))
if __name__=='__main__':sys.exit(main())
