#!/usr/bin/env python3
"""Two workers: independently test objective and exploration changes."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
OUT=ROOT/'runs/policy-confidence-20261021/ablations'

def run(job):
    label,seed=job;name=f'{label}-seed{seed}';out=OUT/name
    if out.exists():raise FileExistsError(out)
    protocol=HERE/f'{label}-protocol.json'
    command=[str(ROOT/'.venv/bin/python'),'-u',str(HERE/'run-joint-stage-v2.py'),'train','--arm','ppo','--seed',str(seed),'--protocol',str(protocol),'--output',str(out)]
    (OUT/f'{name}-command.json').write_text(json.dumps(command,indent=2)+'\n');began=time.time();print('START '+name,flush=True)
    env=dict(os.environ,OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1')
    with (OUT/f'{name}.log').open('w') as log:result=subprocess.run(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
    record=dict(name=name,returncode=result.returncode,elapsed_seconds=time.time()-began)
    (OUT/f'{name}-status.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record),flush=True);return record

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,[(label,seed) for seed in (11,23) for label in ('continuing','low-std')]))
    (OUT/'campaign-status.json').write_text(json.dumps(results,indent=2)+'\n')
    return int(any(r['returncode'] for r in results))
if __name__=='__main__':sys.exit(main())
