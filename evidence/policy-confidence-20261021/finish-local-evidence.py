#!/usr/bin/env python3
"""Wait for ten declared runs; select once; confirm with at most two CPU workers."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from hashlib import sha256
import json,os,shutil,subprocess,sys,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
OUT=ROOT/'runs/policy-confidence-20261021/joint-confirmation'
ENV=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1',NUMEXPR_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1')
def digest(p):return sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text())
def write(p,d):
    with Path(p).open('x') as f:json.dump(d,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
def run_command(label,command):
    write(OUT/(label+'-command.json'),command);started=time.time();print('START '+label,flush=True)
    with (OUT/(label+'.stdout.log')).open('x') as stdout,(OUT/(label+'.stderr.log')).open('x') as stderr:result=subprocess.run(command,cwd=ROOT,env=ENV,stdout=stdout,stderr=stderr)
    receipt=dict(label=label,returncode=result.returncode,elapsed_seconds=time.time()-started,command_sha256=digest(OUT/(label+'-command.json')),stdout_sha256=digest(OUT/(label+'.stdout.log')),stderr_sha256=digest(OUT/(label+'.stderr.log')))
    write(OUT/(label+'-command-receipt.json'),receipt);print(json.dumps(receipt),flush=True)
    if result.returncode:raise RuntimeError(f'{label} failed; inspect preserved stderr/stdout')
    return receipt

def main():
    OUT.mkdir(parents=True,exist_ok=False);began=time.time();protocol=load(HERE/'combined-selection-protocol.json')
    scripts={n:digest(HERE/n) for n in ('finish-local-evidence.py','analyze-joint-stage.py','analyze-confirmation.py','run-confirmation.py','run-joint-stage-v2.py')}
    write(OUT/'launch.json',dict(created_utc=datetime.now(timezone.utc).isoformat(),command=sys.argv,selection_protocol_sha256=digest(HERE/'combined-selection-protocol.json'),scripts=scripts,maximum_workers=2,environment={k:ENV[k] for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS','PYTHONDONTWRITEBYTECODE')}))
    shutil.copyfile(HERE/'combined-selection-protocol.json',OUT/'combined-selection-protocol.json')
    previous=None
    while True:
        status=[]
        for spec in protocol['runs']:
            run=ROOT/spec['path'];path=run/'report.json';d={}
            if path.exists():
                try:d=load(path)
                except json.JSONDecodeError:pass
            statuspath=run.parent/(run.name+'-status.json')
            if statuspath.exists() and load(statuspath)['returncode']!=0:raise RuntimeError(f'training process failed: {run}')
            if d.get('error'):raise RuntimeError(f'training report error: {run}: {d["error"]}')
            status.append(dict(run=spec['path'],complete=bool(d.get('completed')),last_checkpoint=max([c['step'] for c in d.get('checkpoints',[])],default=None)))
        snapshot=json.dumps(status,sort_keys=True)
        if snapshot!=previous:print(snapshot,flush=True);previous=snapshot
        campaigns=[ROOT/'runs/policy-confidence-20261021'/label/'campaign-status.json' for label in ('joint','ablations')]
        if all(s['complete'] for s in status) and all(p.exists() for p in campaigns):
            for path in campaigns:
                assert all(r['returncode']==0 for r in load(path))
            break
        if time.time()-began>8*3600:raise TimeoutError('Training completion not observed within eight hours')
        time.sleep(10)
    for n,pin in scripts.items():assert digest(HERE/n)==pin
    python=str(ROOT/'.venv/bin/python')
    run_command('development-self-check',[python,str(HERE/'analyze-joint-stage.py'),'--self-check'])
    run_command('development-analysis',[python,str(HERE/'analyze-joint-stage.py')])
    shutil.copyfile(HERE/'joint-development.json',OUT/'selection-frozen.json');selection=load(OUT/'selection-frozen.json');selected=selection['selected']
    if selected is None:raise RuntimeError('No development-eligible candidate; confirmation not run')
    run=ROOT/selected['run'];recipe=load(run/'recipe.json');frozen=OUT/'selected-inputs';frozen.mkdir()
    for name in ('recipe.json','source.zip','report.json'):shutil.copyfile(run/name,frozen/name)
    shutil.copyfile(run/selected['checkpoint']['path'],frozen/'checkpoint.zip')
    for name,pin in recipe['inputs'].items():assert digest(name)==pin
    confirmation=dict(schema='cartpole-frozen-confirmation-protocol-v1',declared_utc=datetime.now(timezone.utc).isoformat(),selection_sha256=digest(OUT/'selection-frozen.json'),selection_protocol_sha256=digest(HERE/'combined-selection-protocol.json'),selected=selected,selected_inputs=recipe['inputs'],scripts=scripts,confirmation=protocol['confirmation'],holdout_rule=protocol['holdout_rule'],maximum_workers=2,hardware_accepted=False)
    write(OUT/'confirmation-protocol.json',confirmation);print('FROZEN '+json.dumps(selected),flush=True)
    def evaluate(mode):
        c=protocol['confirmation'];command=[python,str(HERE/'run-confirmation.py'),str(run),'--step',str(selected['step']),'--output',str(OUT/mode),'--mode',mode,'--seconds',str(c[mode+'_seconds']),'--seeds',*[str(s) for s in c[mode+'_seeds']]]
        return run_command(mode,command)
    with ThreadPoolExecutor(max_workers=2) as pool:receipts=list(pool.map(evaluate,('nominal','sdk','stress')))
    for n,pin in scripts.items():assert digest(HERE/n)==pin
    for name,pin in recipe['inputs'].items():assert digest(name)==pin
    run_command('confirmation-analysis',[python,str(HERE/'analyze-confirmation.py')])
    write(OUT/'completion.json',dict(completed=True,elapsed_seconds=time.time()-began,selection_sha256=confirmation['selection_sha256'],summary_sha256=digest(OUT/'summary.json'),receipts=receipts))
    print('COMPLETE '+str(OUT/'summary.json'),flush=True)
if __name__=='__main__':
    try:main()
    except Exception as exc:
        if OUT.exists() and not(OUT/'failure.json').exists():write(OUT/'failure.json',dict(error=repr(exc),traceback=traceback.format_exc()))
        raise
