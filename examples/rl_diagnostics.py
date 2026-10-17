#!/usr/bin/env python3
"""Short offline PPO experiments and summaries; never connect to a rig or Colab."""
import argparse
import json
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    pilot=sub.add_parser('pilot')
    pilot.add_argument('--profile',type=Path,required=True)
    pilot.add_argument('--output',type=Path,required=True)
    pilot.add_argument('--variant',choices=('mixed','upright','upright-scaled','upright-lowstd'),required=True)
    pilot.add_argument('--seed',type=int,required=True)
    pilot.add_argument('--steps',type=int,default=20480)
    pilot.add_argument('--every',type=int,default=10240)
    pilot.add_argument('--seconds',type=float,default=5.)
    pilot.add_argument('--evaluation-seconds',type=float,default=10.)
    pilot.add_argument('--evaluation-seeds',type=int,nargs='+',default=[40000,40001])
    report=sub.add_parser('summarize')
    report.add_argument('pilots',type=Path,nargs='+')
    report.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    from cartpole_sdk.learning.diagnostics import run_pilot,summarize_suite
    from cartpole_sdk.learning.model_experiment import build_experiment,read_json
    try:
        if a.command=='pilot':
            values={key:read_json(a.profile/(key+'.json'))[0] for key in
                    ('executor-parameters','observation-config','prior-parameters')}
            exp=build_experiment(a.profile/'model.json',executor_parameters=values['executor-parameters'],
                observation_config=values['observation-config'],prior_parameters=values['prior-parameters'],
                development_only=True,seconds=a.seconds)
            run_pilot(exp,a.output,variant=a.variant,seed=a.seed,steps=a.steps,every=a.every,
                      evaluation_seconds=a.evaluation_seconds,evaluation_seeds=tuple(a.evaluation_seeds))
        else:
            value=summarize_suite(a.pilots)
            a.output.parent.mkdir(parents=True,exist_ok=True)
            with a.output.open('x') as f:json.dump(value,f,indent=2,allow_nan=False);f.write('\n')
            print(json.dumps(value,indent=2))
    except (ValueError,OSError) as e:
        p.exit(2,str(e)+'\n')

if __name__=='__main__':main()
