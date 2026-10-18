#!/usr/bin/env python3
"""Verify and summarize completed local swing-learning comparisons, retaining failures."""
import argparse
from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def read_run(path):
    path=Path(path);raw=(path/'recipe.json').read_bytes();recipe=json.loads(raw)
    report=json.loads((path/'report.json').read_text())
    if not report['completed'] or sha256(raw).hexdigest()!=report['recipe_sha256']:
        raise ValueError(f'incomplete run or recipe hash mismatch: {path}')
    if any(report.get(k)!=v for k,v in recipe.items()):raise ValueError(f'recipe metadata mismatch: {path}')
    if sha256((path/'source.zip').read_bytes()).hexdigest()!=report['source_zip_sha256']:
        raise ValueError(f'source archive mismatch: {path}')
    if recipe['demonstrations'] and sha256((path/'demonstrations.npz').read_bytes()).hexdigest()!=recipe['demonstrations']['sha256']:
        raise ValueError(f'demonstration mismatch: {path}')
    for row in report['evaluations']:
        checkpoint=path/row['checkpoint']
        if checkpoint.resolve().parent!=(path/'checkpoints').resolve() or sha256(checkpoint.read_bytes()).hexdigest()!=row['checkpoint_sha256']:
            raise ValueError(f'checkpoint mismatch: {path}')
    if report['evaluations'][-1]['steps']!=recipe['steps']:raise ValueError(f'missing final checkpoint: {path}')
    return dict(path=str(path),name=path.name,recipe=recipe,report=report,
                report_sha256=sha256((path/'report.json').read_bytes()).hexdigest())


def summarize(paths,output):
    runs=[read_run(p) for p in paths];groups=defaultdict(list)
    if len({r['recipe']['steps'] for r in runs})!=1:raise ValueError('unequal online budgets')
    if len({json.dumps((r['recipe']['evaluation_seeds'],r['recipe']['evaluation_seconds'])) for r in runs})!=1:raise ValueError('development evaluation protocols differ')
    for r in runs:groups[r['name'].rsplit('-seed',1)[0]].append(r)
    seed_sets=[sorted(r['recipe']['optimizer_seed'] for r in rows) for rows in groups.values()]
    if any(s!=seed_sets[0] or len(set(s))!=len(s) for s in seed_sets):raise ValueError('optimizer seed sets differ or repeat')
    results=[]
    for group,rows in groups.items():
        for index,label in ((0,'initialized'),(-1,'final')):
            for start in ('hanging','upright'):
                episodes=[e for r in rows for e in r['report']['evaluations'][index]['episodes'] if e['start']==start]
                results.append(dict(group=group,checkpoint=label,start=start,episodes=len(episodes),
                    holds=sum(e['hold_success'] for e in episodes),faults=sum(e['fault_reason'] is not None for e in episodes),
                    balanced_fraction=float(np.mean([e['balanced_fraction'] for e in episodes])),
                    tail_x_rms_m=float(np.mean([e['tail_x_rms_m'] for e in episodes])),
                    max_abs_x_m=max(e['max_abs_x_m'] for e in episodes)))
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    summary=dict(schema='cartpole-swing-comparison-v1',hardware_accepted=False,online_steps_per_run=runs[0]['recipe']['steps'],
        optimizer_seeds=seed_sets[0],pose_role='repeatedly inspected development; not qualification',
        evaluation_seeds=runs[0]['recipe']['evaluation_seeds'],
        note='Equal online budgets; supervised initialization uses additional compute and prior information. Every supplied seed and failure retained.',
        source_bindings=[dict(path=r['path'],report_sha256=r['report_sha256'],recipe_sha256=r['report']['recipe_sha256'],
                            source_zip_sha256=r['report']['source_zip_sha256'],final_checkpoint_sha256=r['report']['evaluations'][-1]['checkpoint_sha256']) for r in runs],
        comparisons=results)
    (output/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    labels=list(groups);x=np.arange(len(labels));fig,axes=plt.subplots(1,2,figsize=(12,4.5),sharey=True)
    for ax,start in zip(axes,('hanging','upright')):
        for offset,checkpoint,color in ((-.18,'initialized','#8ab8cc'),(.18,'final','#155c85')):
            rr=[next(r for r in results if r['group']==g and r['start']==start and r['checkpoint']==checkpoint) for g in labels]
            bars=ax.bar(x+offset,[r['holds']/r['episodes'] for r in rr],.34,color=color,label=checkpoint)
            ax.bar_label(bars,labels=[f"{r['holds']}/{r['episodes']}" for r in rr],padding=3,fontsize=9)
        ax.set_title('From hanging' if start=='hanging' else 'From upright')
        ax.set_xticks(x,labels,rotation=25,ha='right');ax.set_ylim(0,1.14);ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
        ax.set_ylabel('Final five-second hold success')
    handles,legend_labels=axes[0].get_legend_handles_labels()
    fig.legend(handles,legend_labels,loc='upper center',bbox_to_anchor=(.5,.91),ncol=2,frameon=False)
    fig.suptitle(f"Swing-up learning • {summary['online_steps_per_run']:,} online decisions per seed • {len(seed_sets[0])} seeds",fontsize=14)
    fig.text(.5,.01,f"{runs[0]['recipe']['evaluation_seconds']:g}-second development episodes; no hardware qualification. Initialization has additional supervised compute.",ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.04,1,.87));fig.savefig(output/'comparison.png',dpi=170);plt.close(fig)
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('runs',type=Path,nargs='+');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    try:summary=summarize(a.runs,a.output)
    except (ValueError,OSError) as e:p.exit(2,str(e)+'\n')
    print(json.dumps(summary['comparisons'],indent=2))

if __name__=='__main__':main()
