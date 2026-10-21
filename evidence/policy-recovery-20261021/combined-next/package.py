#!/usr/bin/env python3
"""Reuse existing immutable Colab bundler/CLI; customize only this new research job."""
import argparse,json
from pathlib import Path
import zipfile
from cartpole_sdk.learning.colab_bundle import prepare_bundle,verify_bundle
from cartpole_sdk.learning.model_experiment import digest
from hashlib import sha256
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def filehash(p):return sha256(p.read_bytes()).hexdigest()
def write(p,v):Path(p).write_text(json.dumps(v,indent=2,sort_keys=True,allow_nan=False)+'\n')
JOB=r'''
# Evidence-only override: ordinary immutable setup, leases, nonce/transport,
# status and packaging come from the existing Colab remote helper above.
def job():
    recipe=json.loads((PROJECT/'inputs/recipe.json').read_text())
    python=str(PROJECT/'.venv/bin/python')
    completed=[];run='runs/combined-'+recipe['combined_budget']
    try:
        for seed in recipe['optimizer_seeds']:
            for arm in recipe['arms']:
                run='runs/combined-'+recipe['combined_budget']+'/'+arm+'-seed'+str(seed)
                write_state(dict(status='training',pid=os.getpid(),run=run,completed_trials=completed,hardware_accepted=False))
                command=[python,'-u',recipe['entrypoint'],'train','--protocol',recipe['combined_protocol'],
                    '--arm',arm,'--seed',str(seed),'--budget',recipe['combined_budget'],'--output',run]
                subprocess.run(command,cwd=PROJECT,check=True,env=dict(os.environ,PYTHONUNBUFFERED='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1'))
                report=PROJECT/run/'report.json'
                if not json.loads(report.read_text()).get('completed'):raise ValueError('trial did not produce a completed report')
                completed.append(dict(arm=arm,seed=seed,run=run,report_sha256=hashlib.sha256(report.read_bytes()).hexdigest()))
        write_state(dict(status='completed',pid=os.getpid(),run=run,completed_trials=completed,hardware_accepted=False))
    except BaseException as error:
        write_state(dict(status='failed',pid=os.getpid(),run=run,error=str(error),completed_trials=completed,hardware_accepted=False))
        raise
'''
def package(output,budget):
    p=json.loads((HERE/'protocol.json').read_text());settings=p['budgets'][budget]
    for name,pin in p['bindings'].items():
        if filehash(ROOT/name)!=pin:raise ValueError('pinned input/source changed: '+name)
    output=Path(output)
    manifest=prepare_bundle(ROOT,HERE/'profile',output,steps=settings['steps'],seed=11,seconds=25.,checkpoint_every=settings['checkpoint_every'],evaluation_seeds=p['development_seeds'])
    recipe=json.loads((output/'recipe.json').read_text())
    recipe.update(entrypoint=str((HERE/'run.py').relative_to(ROOT)),combined_protocol=str((HERE/'protocol.json').relative_to(ROOT)),
        combined_budget=budget,arms=p['arms'],optimizer_seeds=p['optimizer_seeds'],steps_per_trial=settings['steps'],
        total_training_steps=settings['steps']*len(p['arms'])*len(p['optimizer_seeds']),learning_rate=p['hyperparameters']['learning_rate'],
        training_seeds=p['training_seeds'],randomize=False,randomization=None,run='combined-'+budget,
        foundation_actor_content_sha256=json.loads((HERE/'inputs/actor.json').read_text())['content_sha256'],
        protocol_sha256=filehash(HERE/'protocol.json'),hardware_accepted=False)
    write(output/'recipe.json',recipe)
    # Add exactly the new adapter/config/anchor/checkpoint inputs required by
    # its binding manifest; existing source selection remains the bundler's.
    extras=[ROOT/name for name in p['bindings'] if name.startswith(str(HERE.relative_to(ROOT)))]+[HERE/'protocol.json',Path(__file__)]
    with zipfile.ZipFile(output/'source.zip','a',zipfile.ZIP_DEFLATED) as archive:
        existing=set(archive.namelist())
        for path in extras:
            name=str(path.relative_to(ROOT))
            if name not in existing:archive.write(path,name);existing.add(name)
    original=output/'inputs.zip'
    with zipfile.ZipFile(original) as archive:entries={name:archive.read(name) for name in archive.namelist()}
    entries['recipe.json']=(output/'recipe.json').read_bytes()
    temporary=output/'inputs.new.zip'
    with zipfile.ZipFile(temporary,'x',zipfile.ZIP_DEFLATED) as archive:
        for name,data in entries.items():archive.writestr(name,data)
    temporary.replace(original)
    base=(ROOT/'src/cartpole_sdk/learning/colab_remote.py').read_text()
    header,separator,main=base.partition("if __name__ == '__main__':")
    if not separator:raise ValueError('remote helper entrypoint changed')
    old="run = PROJECT/'runs/ppo-001'"
    if header.count(old)!=1:raise ValueError('remote progress path changed')
    header=header.replace(old,"run = PROJECT/state.get('run','runs/combined-'+json.loads((PROJECT/'inputs/recipe.json').read_text())['combined_budget']+'/ppo-seed11')")
    old="for folder in sorted(checkpoints.iterdir()):\n            try:"
    if header.count(old)!=1:raise ValueError('remote checkpoint listing changed')
    header=header.replace(old,"for folder in sorted(checkpoints.iterdir()):\n            if folder.is_file() and folder.suffix=='.zip':\n                state['checkpoints'].append(folder.name)\n                continue\n            try:")
    header=header.replace("'src','examples','scripts','inputs','runs'","'src','examples','scripts','inputs','evidence','runs'")
    pins={name:filehash(output/name) for name in ('source.zip','inputs.zip')}
    remote='EXPECTED_ARCHIVES = '+repr(pins)+'\n'+header+'\n'+JOB+'\n'+separator+main
    compile(remote,str(output/'remote.py'),'exec');(output/'remote.py').write_text(remote)
    manifest.update(recipe=recipe,adapter='Evidence-only combined filtered PPO job override; existing setup/transport/status/package retained.',
        source_files=len(zipfile.ZipFile(output/'source.zip').namelist()),
        files_sha256={name:filehash(output/name) for name in ('source.zip','inputs.zip','recipe.json','remote.py')})
    write(output/'bundle.json',manifest);verify_bundle(output)
    print(json.dumps(dict(bundle=str(output),budget=budget,total_steps=recipe['total_training_steps'],bundle_sha256=filehash(output/'bundle.json'),cloud_started=False)))
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--budget',choices=('pilot','long'),default='pilot');parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();package(args.output,args.budget)
