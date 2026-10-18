#!/usr/bin/env python3
"""Matched local balance learning and longer evaluation. Never connects to hardware."""
import argparse
import json
from pathlib import Path


def read_gains_artifact(path):
    value=json.loads(Path(path).read_text())
    if isinstance(value,dict) and 'schema' in value:
        if value['schema']!='cartpole-observed-balance-teacher-v1':
            raise ValueError('unsupported teacher gains artifact')
        value=value['gains']
    from cartpole_sdk.learning.balance_experiment import teacher_gains
    return teacher_gains(value)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    train=sub.add_parser('train')
    train.add_argument('--profile',type=Path,required=True)
    train.add_argument('--output',type=Path,required=True)
    train.add_argument('--initialization',choices=('scratch','teacher'),required=True)
    train.add_argument('--gains',type=Path)
    train.add_argument('--seed',type=int,required=True)
    train.add_argument('--constraint',choices=('none','equilibrium'),default='none')
    train.add_argument('--steps',type=int,default=20480)
    train.add_argument('--every',type=int,default=10240)
    train.add_argument('--seconds',type=float,default=5.)
    train.add_argument('--evaluation-seconds',type=float,default=10.)
    train.add_argument('--evaluation-seeds',type=int,nargs='+',default=[43000,43001])
    train.add_argument('--learning-rate',type=float,default=.00003)
    train.add_argument('--policy-std',type=float,default=.02)
    train.add_argument('--imitation-updates',type=int,default=1500)
    evaluate=sub.add_parser('evaluate')
    evaluate.add_argument('run',type=Path)
    evaluate.add_argument('--output',type=Path,required=True)
    evaluate.add_argument('--seeds',type=int,nargs='+',required=True)
    evaluate.add_argument('--seconds',type=float,default=60.)
    evaluate.add_argument('--checkpoint',type=int)
    evaluate.add_argument('--starts',nargs='+',choices=('upright','hanging'),default=['upright'])
    a=p.parse_args()
    from cartpole_sdk.learning.balance_experiment import run_trial,evaluate_saved
    from cartpole_sdk.learning.model_experiment import build_experiment,read_json
    try:
        if a.command=='train':
            values={k:read_json(a.profile/(k+'.json'))[0] for k in ('executor-parameters','observation-config','prior-parameters')}
            exp=build_experiment(a.profile/'model.json',executor_parameters=values['executor-parameters'],
                observation_config=values['observation-config'],prior_parameters=values['prior-parameters'],development_only=True,seconds=a.seconds)
            run_trial(exp,a.output,initialization=a.initialization,seed=a.seed,
                gains=read_gains_artifact(a.gains) if a.gains else None,steps=a.steps,every=a.every,constraint=a.constraint,
                evaluation_seeds=tuple(a.evaluation_seeds),evaluation_seconds=a.evaluation_seconds,
                learning_rate=a.learning_rate,policy_std=a.policy_std,imitation_updates=a.imitation_updates)
        else:
            r=evaluate_saved(a.run,a.output,seeds=tuple(a.seeds),seconds=a.seconds,checkpoint=a.checkpoint,starts=tuple(a.starts))
            print(json.dumps(r['by_start'],indent=2))
    except (ValueError,OSError) as e:p.exit(2,str(e)+'\n')

if __name__=='__main__':main()
