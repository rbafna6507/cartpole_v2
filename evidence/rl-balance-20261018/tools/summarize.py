#!/usr/bin/env python3
"""Validate and plot local balance-learning reports; no training or hardware access."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('runs',nargs='+',type=Path)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    rows=[];seen=set();signature=None;teacher_recipe=None
    for folder in a.runs:
        r=json.loads((folder/'report.json').read_text());raw=(folder/'recipe.json').read_bytes();recipe=json.loads(raw)
        if not r['completed'] or sha256(raw).hexdigest()!=r['recipe_sha256'] or any(r.get(k)!=v for k,v in recipe.items()):
            raise ValueError(f'incomplete or mismatched recipe: {folder}')
        if sha256((folder/'source.zip').read_bytes()).hexdigest()!=r['source_zip_sha256']:
            raise ValueError(f'corrupt source archive: {folder}')
        for ev in r['evaluations']:
            cp=folder/ev['checkpoint']
            if cp.parent.resolve()!=(folder/'checkpoints').resolve() or sha256(cp.read_bytes()).hexdigest()!=ev['checkpoint_sha256']:
                raise ValueError(f'corrupt checkpoint: {folder}')
        key=(r['initialization'],r['optimizer_seed'])
        if key in seen:raise ValueError(f'duplicate initialization/seed: {key}')
        seen.add(key)
        sig={k:r[k] for k in ('steps','every','training_seeds','evaluation_seeds','evaluation_seconds','experiment_sha256','provenance','hyperparameters')}
        sig['constraint']=r.get('constraint','none')
        if signature is not None and sig!=signature:raise ValueError('incomparable learning constraints')
        signature=sig
        if r['initialization']=='teacher':
            identity=(r['teacher_gains'],r['imitation_updates'])
            if teacher_recipe is not None and identity!=teacher_recipe:raise ValueError('incomparable teacher recipes')
            teacher_recipe=identity
        rows.append(dict(path=str(folder),initialization=r['initialization'],seed=r['optimizer_seed'],
                         evaluations=r['evaluations'],imitation=r.get('imitation'),wall_seconds=r['wall_seconds']))
    groups={}
    for mode in sorted({r['initialization'] for r in rows}):
        group=[r for r in rows if r['initialization']==mode]
        seeds=sorted(r['seed'] for r in group)
        episodes=[ep for r in group for ep in r['evaluations'][-1]['episodes']]
        groups[mode]=dict(optimizer_seeds=seeds,holds=sum(e['hold_success'] for e in episodes),episodes=len(episodes),
            faults=sum(e['fault_reason'] is not None for e in episodes),
            mean_balanced_fraction=float(np.mean([e['balanced_fraction'] for e in episodes])),
            mean_tail_x_rms_m=float(np.mean([e['tail_x_rms_m'] for e in episodes])),
            worst_cart_peak_m=max(e['max_abs_x_m'] for e in episodes),
            per_seed=[dict(seed=r['seed'],initial=r['evaluations'][0]['by_start'],final=r['evaluations'][-1]['by_start']) for r in group])
    if len({tuple(g['optimizer_seeds']) for g in groups.values()})!=1:raise ValueError('unequal optimizer seed sets')
    a.output.mkdir(parents=True,exist_ok=False)
    summary=dict(schema='cartpole-balance-comparison-v1',groups=groups,hardware_accepted=False,deployable=False,
        note='Equal online budgets, extra supervised compute for teacher initialization. Small development set, no swing-up or transfer qualification.',
        runs=[dict(path=r['path'],wall_seconds=r['wall_seconds'],imitation=r['imitation']) for r in rows],signature=signature)
    (a.output/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    fig,axs=plt.subplots(1,3,figsize=(13,4),constrained_layout=True)
    colors=dict(scratch='#9c495c',teacher='#167a74')
    for r in rows:
        ev=r['evaluations'];c=colors[r['initialization']]; label=f"{r['initialization']} seed {r['seed']}"
        x=[e['steps'] for e in ev]
        axs[0].plot(x,[e['by_start']['upright']['balanced_fraction']*100 for e in ev],'.-',color=c,alpha=.75,label=label)
        axs[1].plot(x,[e['by_start']['upright']['tail_x_rms_m']*100 for e in ev],'.-',color=c,alpha=.75)
        axs[2].plot(x,[e['by_start']['upright']['holds']/e['by_start']['upright']['episodes']*100 for e in ev],'.-',color=c,alpha=.75)
    for ax in axs:ax.set_xlabel('PPO simulator decisions');ax.grid(alpha=.2)
    axs[0].set_ylabel('Time balanced (%)');axs[1].set_ylabel('Final-window cart RMS (cm)');axs[2].set_ylabel('Final 5 s hold success (%)')
    axs[0].legend(fontsize=8);fig.suptitle('Nominal encoder balance • development cases • 150 m/s³ jerk')
    fig.savefig(a.output/'learning.png',dpi=160);plt.close(fig)
    print(json.dumps(groups,indent=2))

if __name__=='__main__':main()
