#!/usr/bin/env python3
"""Local observed-state swing-up and balance training; no hardware commands."""
import argparse,json
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    t=sub.add_parser('train');t.add_argument('--profile',type=Path,required=True);t.add_argument('--output',type=Path,required=True)
    t.add_argument('--initialization',choices=('scratch','balance','demonstrations'),required=True);t.add_argument('--seed',type=int,required=True)
    t.add_argument('--steps',type=int,default=20480);t.add_argument('--every',type=int,default=10240)
    t.add_argument('--reset-mode',choices=('mixed','curriculum'),default='mixed');t.add_argument('--seconds',type=float,default=10.)
    t.add_argument('--learning-rate',type=float,default=.000003);t.add_argument('--policy-std',type=float,default=.05)
    t.add_argument('--evaluation-seconds',type=float,default=25.);t.add_argument('--evaluation-seeds',type=int,nargs='+',default=[53000,53001])
    t.add_argument('--demonstrations',type=Path);t.add_argument('--train-episodes',type=int,nargs='+',default=[])
    t.add_argument('--validation-episodes',type=int,nargs='+',default=[]);t.add_argument('--imitation-updates',type=int,default=3000)
    t.add_argument('--balance-anchor-weight',type=float,default=0.)
    e=sub.add_parser('evaluate');e.add_argument('run',type=Path);e.add_argument('--output',type=Path,required=True)
    e.add_argument('--seeds',type=int,nargs='+',required=True);e.add_argument('--seconds',type=float,default=60.)
    e.add_argument('--checkpoint',type=int);e.add_argument('--starts',choices=('hanging','upright'),nargs='+',default=['hanging','upright'])
    a=p.parse_args()
    from cartpole_sdk.learning.swing_experiment import run_trial,evaluate_saved
    from cartpole_sdk.learning.model_experiment import build_experiment,read_json
    try:
        if a.command=='train':
            inputs={k:read_json(a.profile/(k+'.json'))[0] for k in ('executor-parameters','observation-config','prior-parameters')}
            exp=build_experiment(a.profile/'model.json',executor_parameters=inputs['executor-parameters'],observation_config=inputs['observation-config'],prior_parameters=inputs['prior-parameters'],development_only=True,seconds=a.seconds)
            run_trial(exp,a.output,initialization=a.initialization,seed=a.seed,steps=a.steps,every=a.every,reset_mode=a.reset_mode,
                learning_rate=a.learning_rate,policy_std=a.policy_std,evaluation_seconds=a.evaluation_seconds,evaluation_seeds=tuple(a.evaluation_seeds),
                demonstrations=a.demonstrations,train_episodes=tuple(a.train_episodes),validation_episodes=tuple(a.validation_episodes),imitation_updates=a.imitation_updates,balance_anchor_weight=a.balance_anchor_weight)
        else:print(json.dumps(evaluate_saved(a.run,a.output,seeds=tuple(a.seeds),seconds=a.seconds,checkpoint=a.checkpoint,starts=tuple(a.starts))['by_start'],indent=2))
    except (ValueError,OSError) as error:p.exit(2,str(error)+'\n')

if __name__=='__main__':main()
