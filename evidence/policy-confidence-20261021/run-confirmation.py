#!/usr/bin/env python3
"""Validate a frozen checkpoint on unseen starts, stress, or actual SDK inference.

Use the project's RL Python. A separate binding receipt verifies the original
source archive and allows only the reviewed evaluator-file revision; training
and inference runtime hashes must still match. No hardware is contacted.
"""
import argparse
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import zipfile
import torch
from cartpole_sdk.learning.candidate_parity import check_candidate
from cartpole_sdk.learning.projected_ppo import EquilibriumPPO
from cartpole_sdk.learning.retained_ppo import RetainedPPO

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent

def digest(path):return sha256(Path(path).read_bytes()).hexdigest()

def load_driver():
    spec=importlib.util.spec_from_file_location('confidence_evaluator_v2',HERE/'run-joint-stage-v2.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def verified_checkpoint(run,step):
    recipe=json.loads((run/'recipe.json').read_text());report=json.loads((run/'report.json').read_text())
    if not report['completed'] or digest(run/'recipe.json')!=report['recipe_sha256']:raise ValueError('incomplete run or changed recipe')
    if digest(run/'source.zip')!=report['source_zip_sha256']:raise ValueError('source archive changed')
    evaluator=load_driver();current=evaluator.sources();original=recipe['source']
    if {k:v for k,v in original.items() if k!='driver'}!={k:v for k,v in current.items() if k!='driver'}:
        raise ValueError('training or inference runtime changed; only reviewed evaluator revision allowed')
    with zipfile.ZipFile(run/'source.zip') as archive:
        archived=sha256(archive.read('confidence/run-joint-stage.py')).hexdigest()
    if archived!=original['driver']:raise ValueError('archived driver differs from recipe')
    matches=[r for r in report['checkpoints'] if r['step']==step]
    if len(matches)!=1:raise ValueError('checkpoint step absent or duplicated')
    checkpoint=matches[0];path=run/checkpoint['path']
    if path.parent.resolve()!=(run/'checkpoints').resolve() or digest(path)!=checkpoint['sha256']:raise ValueError('checkpoint path/hash mismatch')
    klass=RetainedPPO if recipe['arm']=='retained' else EquilibriumPPO
    model=klass.load(path,device='cpu')
    if evaluator.robust.actor_weights_hash(model)!=checkpoint['actor_weights_sha256']:raise ValueError('loaded actor weights differ from checkpoint receipt')
    binding=dict(run=str(run.resolve()),step=step,checkpoint=checkpoint,recipe_sha256=report['recipe_sha256'],
        source_zip_sha256=report['source_zip_sha256'],original_source=original,evaluation_source=current,
        change='Reviewed v2 evaluator preserves early faults with unavailable tail metrics as null; all training/inference source identities match.',
        confirmation_driver_sha256=digest(__file__))
    return model,recipe,evaluator,binding

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--step',type=int,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seeds',type=int,nargs='+',required=True)
    p.add_argument('--seconds',type=float,default=60.);p.add_argument('--mode',choices=('nominal','stress','sdk'),default='nominal')
    args=p.parse_args();torch.set_num_threads(1)
    if not 5<=args.seconds<=60 or round(args.seconds*100)!=args.seconds*100:raise ValueError('seconds must contain whole 100Hz decisions in5..60')
    model,recipe,evaluator,binding=verified_checkpoint(args.run,args.step)
    train=recipe['protocol']['training_seeds']
    used=set(range(train[0],train[1]+1))|set(recipe['protocol']['development_seeds'])|evaluator.robust.PRIOR_USED_SEEDS|set(range(95000,95004))
    if any(s<0 for s in args.seeds) or len(set(args.seeds))!=len(args.seeds) or set(args.seeds)&used:raise ValueError('fresh nonnegative independent pose seeds required')
    args.output.mkdir(parents=True,exist_ok=False)
    binding.update(mode=args.mode,seeds=args.seeds,seconds=args.seconds,hardware_accepted=False)
    (args.output/'binding.json').write_text(json.dumps(binding,indent=2)+'\n')
    if args.mode=='sdk':
        result=check_candidate(model,recipe['experiment'],args.output/'evaluation',checkpoint_sha256=binding['checkpoint']['sha256'],seeds=tuple(args.seeds),seconds=args.seconds)
        summary={k:result[k] for k in ('compared_actions','max_abs_raw_discrepancy_m_s2','emission_parity_pass','task_hold_successes')}
    else:
        result=evaluator.evaluate(model,recipe['experiment'],args.output/'evaluation',args.seeds,args.seconds,binding['checkpoint']['sha256'],stress=args.mode=='stress')
        summary=result['summary']
    (args.output/'receipt.json').write_text(json.dumps(dict(binding_sha256=digest(args.output/'binding.json'),report_sha256=digest(args.output/'evaluation/report.json'),completed=result['completed']),indent=2)+'\n')
    print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
