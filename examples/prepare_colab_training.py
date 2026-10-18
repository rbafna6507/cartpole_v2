#!/usr/bin/env python3
"""Validate and package a selected training profile; never connects to Colab or the rig."""
import argparse
import json
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--profile',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--steps',type=int,default=2097152)
    p.add_argument('--seed',type=int,default=20261017)
    p.add_argument('--seconds',type=float,default=25.)
    p.add_argument('--checkpoint-every',type=int,default=102400)
    p.add_argument('--evaluation-seeds',type=int,nargs='+',default=list(range(20000,20016)))
    a=p.parse_args()
    from cartpole_sdk.learning.colab_bundle import prepare_bundle
    try:
        result=prepare_bundle(Path(__file__).resolve().parents[1],a.profile,a.output,
                              steps=a.steps,seed=a.seed,seconds=a.seconds,
                              checkpoint_every=a.checkpoint_every,evaluation_seeds=tuple(a.evaluation_seeds))
    except (ValueError,OSError) as error:
        p.exit(2,str(error)+'\n')
    print(json.dumps(dict(bundle=str(a.output),recipe=result['recipe'],hardware_accepted=False),indent=2))

if __name__=='__main__':main()
