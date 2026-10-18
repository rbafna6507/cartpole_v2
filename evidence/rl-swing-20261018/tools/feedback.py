#!/usr/bin/env python3
"""Record local actor feedback derivatives from hash-verified trusted checkpoints."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import torch
from stable_baselines3 import PPO


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('runs',nargs='+',type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    torch.set_num_threads(1);rows=[]
    for run in a.runs:
        report=json.loads((run/'report.json').read_text())
        for row in (report['evaluations'][0],report['evaluations'][-1]):
            cp=run/row['checkpoint']
            if cp.resolve().parent!=(run/'checkpoints').resolve() or sha256(cp.read_bytes()).hexdigest()!=row['checkpoint_sha256']:raise ValueError('checkpoint mismatch')
            model=PPO.load(cp,device='cpu')
            q=torch.tensor([[0.,0.,0.,1.,0.,0.,0.]],requires_grad=True)
            action=model.policy.get_distribution(dict(state=q,valid=torch.ones((1,7)),age_s=torch.zeros((1,7)))).distribution.mean*25.
            action.backward()
            rows.append(dict(run=str(run),steps=row['steps'],checkpoint_sha256=row['checkpoint_sha256'],
                equilibrium_raw_action_m_s2=float(action.detach().item()),derivatives=dict(zip(('x','v','sin_theta','cos_theta','omega','previous_acceleration','rail_brake'),q.grad[0].tolist()))))
    result=dict(schema='cartpole-local-feedback-diagnostic-v1',rows=rows,
        scope='Autograd at observed upright equilibrium. Local derivatives of the actor only, not stability proof or full closed-loop plant linearization.',
        angle_interpretation='At theta=0, derivative with respect to sin(theta) equals first-order angle feedback; cos(theta) has zero first-order angle variation.',
        action_scale_m_s2=25.,hardware_accepted=False)
    with a.output.open('x') as f:json.dump(result,f,indent=2,allow_nan=False);f.write('\n')

if __name__=='__main__':main()
