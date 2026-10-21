#!/usr/bin/env python3
"""Verify completed joint runs; select on development only before fresh tests."""
from hashlib import sha256
import json
import math
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent

def hashed(path):return sha256(path.read_bytes()).hexdigest()

def main():
    protocol=json.loads((HERE/'joint-protocol.json').read_text());rows=[];candidates=[]
    for seed in protocol['optimizer_seeds']:
        for arm in protocol['arms']:
            run=ROOT/f'runs/policy-confidence-20261021/joint/{arm}-seed{seed}'
            report=json.loads((run/'report.json').read_text());recipe=json.loads((run/'recipe.json').read_text())
            assert report['completed'] and hashed(run/'recipe.json')==report['recipe_sha256']
            assert hashed(run/'source.zip')==report['source_zip_sha256']
            for evaluation in report['evaluations']:
                path=run/evaluation['path'];assert hashed(path)==evaluation['sha256']
                result=json.loads(path.read_text());assert result['completed']
                cp=next(r for r in report['checkpoints'] if r['step']==evaluation['step'])
                assert hashed(run/cp['path'])==cp['sha256']
                episodes=result['episodes']
                for start in ('hanging','upright'):
                    group=[e for e in episodes if e['start']==start]
                    row=dict(arm=arm,optimizer_seed=seed,step=evaluation['step'],start=start,episodes=len(group),
                        holds=sum(e['hold_success'] for e in group),full_balance=sum(e['balanced_fraction']>=1.-1e-12 for e in group),
                        faults=sum(e['fault_reason'] is not None for e in group),
                        captures=[e['first_one_second_capture_s'] for e in group],
                        mean_balanced_fraction=float(np.mean([e['balanced_fraction'] for e in group])),
                        mean_longest_dwell_s=float(np.mean([e['longest_balance_dwell_s'] for e in group])),
                        worst_max_abs_x_m=max(e['max_abs_x_m'] for e in group),
                        tail_x_rms_m=[e['final_window_x_rms_m'] for e in group])
                    rows.append(row)
                up=[e for e in episodes if e['start']=='upright'];hang=[e for e in episodes if e['start']=='hanging']
                eligible=all(e['balanced_fraction']>=1.-1e-12 for e in up) and all(e['fault_reason'] is None for e in episodes)
                captures=[e['first_one_second_capture_s'] for e in hang if e['hold_success']]
                rank=[sum(e['hold_success'] for e in hang),-float(np.mean(captures)) if captures else -1e9,
                      float(np.mean([e['longest_balance_dwell_s'] for e in hang]))]
                candidates.append(dict(run=str(run.relative_to(ROOT)),step=evaluation['step'],checkpoint=cp,
                    eligible=eligible,rank=rank,development_evaluation_sha256=evaluation['sha256']))
    eligible=[c for c in candidates if c['eligible']]
    # Stable iteration order breaks exact ties; duplicate initial weights are one control.
    selected=max(eligible,key=lambda c:tuple(c['rank'])) if eligible else None
    result=dict(schema='cartpole-joint-development-selection-v1',hardware_accepted=False,rows=rows,candidates=candidates,selected=selected,
        scope='Development selection only. Repeated optimizer-seed counts share the same two poses; no hardware success probability.',
        selection='Require fault-free evaluation and both upright poses balanced throughout. Rank hanging final holds, mean capture time among held episodes, then longest dwell. Initial actor eligible.',
        future_confirmation_seeds=protocol['future_confirmation_seeds'],analyzer_sha256=hashed(Path(__file__)))
    path=HERE/'joint-development.json'
    with path.open('x') as stream:json.dump(result,stream,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps(selected,indent=2))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(11,4),layout='constrained')
    colors={'ppo':'#bb5936','retained':'#176d79'}
    for arm in protocol['arms']:
        for seed in protocol['optimizer_seeds']:
            for ax,start in zip(axes,('hanging','upright')):
                r=[r for r in rows if r['arm']==arm and r['optimizer_seed']==seed and r['start']==start]
                ax.plot([v['step'] for v in r],[v['holds']/v['episodes'] for v in r],marker='o',color=colors[arm],alpha=.7,label=f'{arm} seed{seed}')
    for ax,title in zip(axes,('Hanging-start final holds','Upright-start final holds')):
        ax.set(title=title,xlabel='Online training decisions',ylabel='Fraction of two development poses',ylim=(-.05,1.05));ax.grid(alpha=.2)
    axes[0].legend(fontsize=8,ncol=2)
    fig.suptitle('Joint policy: improvement must exceed the initial checkpoint')
    fig.savefig(HERE/'joint-development.png',dpi=170)
if __name__=='__main__':main()
