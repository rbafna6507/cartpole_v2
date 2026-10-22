#!/usr/bin/env python3
"""Continue a verified combined PPO checkpoint; original evidence stays immutable."""
import argparse
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import shutil
import time
import zipfile
import torch
from stable_baselines3.common.logger import configure
from stable_baselines3.common.utils import set_random_seed

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
OLD=HERE.parent/'combined-next'
spec=importlib.util.spec_from_file_location('frozen_combined',OLD/'run.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)

def remaining_steps(start,end,every):
    if any(type(v) is not int for v in (start,end,every)) or every<=0 or not 0<start<end or start%every or end%every:
        raise ValueError('invalid absolute continuation budget')
    return list(range(start+every,end+1,every))

def load_resume(report_path,report_sha,checkpoint,p,step):
    if base.digest(report_path)!=report_sha:raise ValueError('source report hash mismatch')
    report=json.loads(Path(report_path).read_text())
    if report['protocol_sha256']!=base.digest(OLD/'protocol.json') or report['arm']!='ppo' or report['optimizer_seed']!=11 or report['budget']!='long':
        raise ValueError('source report identity mismatch')
    rows=[r for r in report['checkpoints'] if r['step']==step]
    if len(rows)!=1 or base.digest(checkpoint)!=rows[0]['sha256']:raise ValueError('checkpoint binding mismatch')
    with zipfile.ZipFile(checkpoint) as z:
        if z.testzip() is not None:raise ValueError('checkpoint CRC failed')
    model=base.EquilibriumPPO.load(checkpoint,device='cpu',force_reset=True)
    row=rows[0]
    if model.num_timesteps!=step or base.model_weights_sha256(model)!=row['weights_sha256'] or base.actor_weights_hash(model)!=row['actor_weights_sha256']:
        raise ValueError('checkpoint weights/counter mismatch')
    h=p['hyperparameters']
    for name in ('n_steps','batch_size','n_epochs','gamma','gae_lambda'):
        if getattr(model,name)!=h[name]:raise ValueError('checkpoint hyperparameter mismatch: '+name)
    if model.learning_rate!=h['learning_rate'] or not model.policy.optimizer.state_dict()['state']:
        raise ValueError('checkpoint optimizer missing or learning rate mismatch')
    receipt=dict(source_report_sha256=report_sha,source_checkpoint_sha256=row['sha256'],step=step,
        optimizer_restored=True,critic_restored=True,counters_restored=True,bit_exact_resume=False,
        limitation='Saved PPO state includes weights/Adam/counters, not MuJoCo environment or global RNG. Start a fresh training episode and seed global RNG explicitly.',
        restart_rng_seed=20261021+step)
    return model,receipt

def train_resume(manifest_path,output):
    manifest=json.loads(Path(manifest_path).read_text())
    for name,pin in manifest['bindings'].items():
        if base.digest(ROOT/name)!=pin:raise ValueError('recovery source changed: '+name)
    p=base.protocol(OLD/'protocol.json');torch.set_num_threads(1)
    report_path=ROOT/manifest['source_report'];checkpoint=ROOT/manifest['checkpoint']
    model,receipt=load_resume(report_path,manifest['source_report_sha256'],checkpoint,p,manifest['step'])
    schedule=remaining_steps(manifest['step'],p['budgets']['long']['steps'],p['budgets']['long']['checkpoint_every'])
    output=Path(output);output.mkdir(parents=True,exist_ok=False);(output/'checkpoints').mkdir()
    report=json.loads(report_path.read_text())
    for row in report['checkpoints']:
        src=checkpoint.parent/Path(row['path']).name
        if base.digest(src)!=row['sha256']:raise ValueError('prior checkpoint mismatch')
        shutil.copyfile(src,output/row['path'])
    report.update(completed=False,optimizer_resume=True,resume=receipt,
        recovery_manifest_sha256=base.digest(manifest_path),recovery_adapter_sha256=base.digest(__file__),
        steps_completed=manifest['step'],prior_evaluation_trace_availability='Prior evaluation summaries/hashes preserved; original cloud traces were not backed up.',
        transfer='Full checkpoint continuation. Original foundation transfer is documented in source report.')
    base.write(output/'recipe.json',dict(protocol=p,recovery=manifest))
    base.atomic(output/'report.json',report)
    env=base.TrainingEnv(deepcopy(p['experiment']),p['training_seeds'],reward_scale=.01)
    model.set_env(env,force_reset=True)
    set_random_seed(receipt['restart_rng_seed'])
    model.set_logger(configure(str(output/'logs'),['csv']))
    began=time.monotonic()
    try:
        for step in schedule:
            model.learn(total_timesteps=p['budgets']['long']['checkpoint_every'],reset_num_timesteps=False,
                        callback=base.Episodes(output/'training-episodes.jsonl'))
            if model.num_timesteps!=step:raise ValueError('absolute progress counter mismatch')
            base.protocol(OLD/'protocol.json')
            cp=output/'checkpoints'/f'step-{step:09d}.zip';model.save(cp)
            row=dict(step=step,path=str(cp.relative_to(output)),sha256=base.digest(cp),
                     actor_weights_sha256=base.actor_weights_hash(model),weights_sha256=base.model_weights_sha256(model))
            report['checkpoints'].append(row);report['steps_completed']=step;base.atomic(output/'report.json',report)
            if step in p['budgets']['long']['evaluate_at']:
                result=base.evaluate(model,p,output/f'eval-{step:09d}',seconds=p['development_seconds'],
                    checkpoint_sha256=row['sha256'],protocol_sha256=base.digest(OLD/'protocol.json'))
                report['evaluations'].append(dict(step=step,path=f'eval-{step:09d}/report.json',
                    sha256=base.digest(output/f'eval-{step:09d}/report.json'),summary=result['summary']))
            model.logger.record('time/total_timesteps',step);model.logger.dump(step=step)
            base.atomic(output/'report.json',report)
            print(json.dumps(dict(step=step,resumed_from=manifest['step'])),flush=True)
        reloaded=base.EquilibriumPPO.load(cp,device='cpu')
        if base.model_weights_sha256(reloaded)!=base.model_weights_sha256(model):raise ValueError('roundtrip mismatch')
        parity=base.check_candidate(reloaded,p['experiment'],output/'final-emission-parity',checkpoint_sha256=base.digest(cp),
            seeds=p['development_seeds'][:2],seconds=5.)
        if not parity['emission_parity_pass'] or parity['rejected_inputs']:raise ValueError('SDK parity failed')
        report.update(completed=True,resumed_wall_seconds=time.monotonic()-began,checkpoint_roundtrip=True,
            final_emission_parity=dict(passed=True,max_abs_raw_error_m_s2=parity['max_abs_raw_discrepancy_m_s2']))
        base.atomic(output/'report.json',report)
    except BaseException as error:
        report['error']=str(error);base.atomic(output/'report.json',report);raise
    finally:env.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,default=HERE/'manifest.json')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();train_resume(args.manifest,args.output)
