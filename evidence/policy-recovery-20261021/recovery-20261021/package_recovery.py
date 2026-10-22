#!/usr/bin/env python3
"""Build a new immutable continuation bundle from verified original artifacts."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile
from cartpole_sdk.learning.colab_bundle import verify_bundle
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
OLD=HERE.parent/'combined-next'
SESSION='filtered-bal-joint-recovery-20261021'

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):Path(path).write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')

def trial_commands(python):
    trials=[]
    for seed in (11,23,47):
        for arm in ('ppo','retained'):
            run=f'runs/combined-long/{arm}-seed{seed}'
            if seed==11 and arm=='ppo':
                command=[python,'-u',str(HERE.relative_to(ROOT)/'resume.py'),'--manifest',str(HERE.relative_to(ROOT)/'manifest.json'),'--output',run]
            else:
                command=[python,'-u',str(OLD.relative_to(ROOT)/'run.py'),'train','--protocol',str(OLD.relative_to(ROOT)/'protocol.json'),
                         '--arm',arm,'--seed',str(seed),'--budget','long','--output',run]
            trials.append(dict(arm=arm,seed=seed,run=run,command=command))
    return trials

FOREGROUND=r'''
def run():
    # The notebook cell executes real training until completion. No idle keepalive.
    (PROJECT/'job-launch.lock').mkdir(exist_ok=False)
    with (PROJECT/'training.log').open('xb') as stream:
        process=subprocess.Popen([sys.executable,'-u','/content/cartpole-launch.py','job'],
            cwd=PROJECT,stdout=stream,stderr=subprocess.STDOUT)
        print('CARTPOLE_FOREGROUND_STARTED '+json.dumps(dict(pid=process.pid)),flush=True)
        code=process.wait()
    if code:raise RuntimeError('training supervisor exited '+str(code))
'''
JOB=r'''
def job():
    recipe=json.loads((PROJECT/'inputs/recipe.json').read_text())
    completed=[];run=recipe['recovery_trials'][0]['run']
    try:
        for trial in recipe['recovery_trials']:
            run=trial['run']
            write_state(dict(status='training',pid=os.getpid(),run=run,completed_trials=completed,hardware_accepted=False,
                resumed_from=460800,recovery_manifest_sha256=recipe['recovery_manifest_sha256']))
            subprocess.run(trial['command'],cwd=PROJECT,check=True,
                env=dict(os.environ,PYTHONUNBUFFERED='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1'))
            report=PROJECT/run/'report.json'
            if not json.loads(report.read_text()).get('completed'):raise ValueError('trial did not complete')
            completed.append(dict(arm=trial['arm'],seed=trial['seed'],run=run,report_sha256=hashlib.sha256(report.read_bytes()).hexdigest()))
        write_state(dict(status='completed',pid=os.getpid(),run=run,completed_trials=completed,hardware_accepted=False))
    except BaseException as error:
        write_state(dict(status='failed',pid=os.getpid(),run=run,error=str(error),completed_trials=completed,hardware_accepted=False))
        raise
'''

def package(output):
    original=OLD/'colab-long-final';verify_bundle(original)
    backup=ROOT/'runs/colab-filtered-joint-long-20261021-checkpoints'
    last=json.loads((backup/'last-complete.json').read_text());ref=last['reports'][0]
    source_report=backup/ref['local_path']
    if digest(source_report)!=ref['sha256']:raise ValueError('source report changed')
    report=json.loads(source_report.read_text())
    inputs=HERE/'inputs';inputs.mkdir(exist_ok=False);(inputs/'checkpoints').mkdir()
    shutil.copyfile(source_report,inputs/'report.json')
    for row in report['checkpoints']:
        source=backup/ref['run']/row['path']
        if digest(source)!=row['sha256']:raise ValueError('checkpoint SHA failed')
        with zipfile.ZipFile(source) as z:
            if z.testzip() is not None:raise ValueError('checkpoint CRC failed')
        shutil.copyfile(source,inputs/'checkpoints'/source.name)
    step=max(r['step'] for r in report['checkpoints'])
    if step!=460800:raise ValueError('unexpected recovery point')
    files=[HERE/'resume.py',Path(__file__),HERE/'watch.py',*inputs.rglob('*.json'),*inputs.rglob('*.zip')]
    manifest=dict(schema='cartpole-combined-recovery-v1',original_bundle_sha256=digest(original/'bundle.json'),
        protocol_sha256=digest(OLD/'protocol.json'),source_report=str((inputs/'report.json').relative_to(ROOT)),
        source_report_sha256=ref['sha256'],checkpoint=str((inputs/'checkpoints'/f'step-{step:09d}.zip').relative_to(ROOT)),
        step=step,session=SESSION,bindings={str(f.relative_to(ROOT)):digest(f) for f in files})
    write(HERE/'manifest.json',manifest)
    output=Path(output);shutil.copytree(original,output)
    with zipfile.ZipFile(output/'source.zip','a',zipfile.ZIP_DEFLATED) as z:
        existing=set(z.namelist())
        for f in [*files,HERE/'manifest.json']:
            name=str(f.relative_to(ROOT))
            if name in existing:raise ValueError('source archive would replace original member')
            z.write(f,name)
    recipe=json.loads((output/'recipe.json').read_text())
    recipe.update(recovery_manifest_sha256=digest(HERE/'manifest.json'),recovery_trials=trial_commands('/content/cartpole-training/.venv/bin/python'),
        resumed_steps=460800,remaining_training_steps=5683200,launch_mode='foreground real training cell')
    write(output/'recipe.json',recipe)
    with zipfile.ZipFile(output/'inputs.zip') as z:entries={n:z.read(n) for n in z.namelist()}
    entries['recipe.json']=(output/'recipe.json').read_bytes()
    with zipfile.ZipFile(output/'inputs.new.zip','x',zipfile.ZIP_DEFLATED) as z:
        for name,data in entries.items():z.writestr(name,data)
    (output/'inputs.new.zip').replace(output/'inputs.zip')
    remote=(original/'remote.py').read_text()
    header,sep,main=remote.partition("if __name__ == '__main__':")
    header=header[header.index('\n')+1:]
    pins={name:digest(output/name) for name in ('source.zip','inputs.zip')}
    main=main.replace("'setup','start','status','package','job'","'setup','run','status','package','job'")
    remote='EXPECTED_ARCHIVES = '+repr(pins)+'\n'+header+'\n'+JOB+'\n'+FOREGROUND+'\n'+sep+main
    compile(remote,str(output/'remote.py'),'exec');(output/'remote.py').write_text(remote)
    bundle=json.loads((output/'bundle.json').read_text())
    bundle.update(recipe=recipe,adapter='Full PPO-state recovery with genuine foreground training execution',
        source_files=len(zipfile.ZipFile(output/'source.zip').namelist()),
        files_sha256={name:digest(output/name) for name in ('source.zip','inputs.zip','recipe.json','remote.py')})
    write(output/'bundle.json',bundle);verify_bundle(output)
    print(json.dumps(dict(bundle=str(output),bundle_sha256=digest(output/'bundle.json'),session=SESSION,resume_step=step)))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    package(parser.parse_args().output)
