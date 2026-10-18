#!/usr/bin/env python3
"""Summarize the complete October 18 experiment cycle with all optimizer seeds."""
import argparse,json
from pathlib import Path
from hashlib import sha256
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--runs',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 reports={}
 for file in sorted(a.runs.glob('*/report.json')):
  r=json.loads(file.read_text())
  if r.get('schema')!='cartpole-balance-learning-v1':continue
  folder=file.parent;raw=(folder/'recipe.json').read_bytes();recipe=json.loads(raw)
  if not r['completed'] or sha256(raw).hexdigest()!=r['recipe_sha256'] or any(r.get(k)!=v for k,v in recipe.items()):raise ValueError('bad training report')
  if sha256((folder/'source.zip').read_bytes()).hexdigest()!=r['source_zip_sha256']:raise ValueError('source hash')
  for ev in r['evaluations']:
   cp=folder/ev['checkpoint']
   if cp.parent.resolve()!=(folder/'checkpoints').resolve() or sha256(cp.read_bytes()).hexdigest()!=ev['checkpoint_sha256']:raise ValueError('checkpoint hash')
  reports[folder.name]=r
 phases=[('Scratch','scratch',-1),('Teacher only','teacher-v1',0),('Teacher + PPO','teacher-v1',-1),
   ('Lower LR only','teacher-slow',-1),('Scratch + projection','projected-scratch',-1),
   ('Teacher + projection','projected-teacher',-1),('Teacher + projection\n+ lower LR','projected-slow',-1)]
 summaries=[]
 for name,prefix,index in phases:
  runs=[reports[f'{prefix}-seed{s}'] for s in (3,17,29)]
  eps=[ep for r in runs for ep in r['evaluations'][index]['episodes']]
  summaries.append(dict(method=name.replace('\n',' '),optimizer_seeds=[3,17,29],steps=runs[0]['evaluations'][index]['steps'],
   holds=sum(ep['hold_success'] for ep in eps),episodes=len(eps),balanced_fraction=float(np.mean([ep['balanced_fraction'] for ep in eps])),
   faults=sum(ep['fault_reason'] is not None for ep in eps),mean_tail_x_rms_m=float(np.mean([ep['tail_x_rms_m'] for ep in eps])),
   per_seed=[dict(seed=s,metrics=r['evaluations'][index]['by_start']['upright']) for s,r in zip((3,17,29),runs)]))
 long=[];hanging=[];raw=[]
 for seed in (3,17,29):
  for prefix,rows in [('long-projected',long),('hanging-projected',hanging)]:
   file=a.runs/f'{prefix}-seed{seed}'/'evaluation.json';r=json.loads(file.read_text());rp=json.loads((file.parent/'replay-provenance.json').read_text())
   if sha256(file.read_bytes()).hexdigest()!=rp['evaluation_sha256']:raise ValueError('evaluation hash')
   cp=reports[f'projected-slow-seed{seed}']['evaluations'][-1]['checkpoint_sha256']
   if r['checkpoint_sha256']!=cp or rp['checkpoint_sha256']!=cp:raise ValueError('evaluation checkpoint mismatch')
   rows.append(dict(optimizer_seed=seed,summary=r['by_start'],episode_metrics=[{k:v for k,v in e.items() if k!='trajectory'} for e in r['episodes']]))
   if prefix=='long-projected':raw.extend((seed,e) for e in r['episodes'])
 result=dict(training_trials=len(reports),training_decisions=sum(r['steps'] for r in reports.values()),phases=summaries,
  long_evaluation=long,hanging_probes=hanging,hardware_accepted=False,deployable=False,
  note='Adaptive short experimental cycle; nominal small upright resets only. Retention is not evidence of improvement over the initialized teacher. Hanging probes are not training.')
 a.output.mkdir(parents=True,exist_ok=True);(a.output/'cycle-summary.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
 plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
 fig,axs=plt.subplots(2,2,figsize=(13,8),constrained_layout=True)
 colors=['#a85161','#7c91a5','#c88442','#ad9a84','#a85161','#7176ac','#167a74']
 ax=axs[0,0];ax.barh(range(len(summaries)),[r['holds'] for r in summaries],color=colors)
 ax.set_yticks(range(len(summaries)),[r[0] for r in phases]);ax.invert_yaxis();ax.set_xlim(0,6.8)
 for i,r in enumerate(summaries):ax.text(r['holds']+.12,i,f"{r['holds']}/6",va='center')
 ax.set_xlabel('Successful final 5 s holds (10 s development episodes)');ax.set_title('All three training seeds • equal 20,480 PPO decisions*')
 cmap={3:'#167a74',17:'#5b6db1',29:'#c17b35'}
 for seed,ep in raw:
  trace=ep['trajectory'];t=[r['t'] for r in trace];x=[r['x']*1000 for r in trace]
  axs[0,1].plot(t,x,color=cmap[seed],alpha=.42,linewidth=.8)
 for sign in (-1,1):axs[0,1].axhline(sign*120,color='#a85161',linestyle='--',alpha=.65)
 axs[0,1].set(xlabel='Time (s)',ylabel='Cart position (mm)',title='Final candidates: 24 unseen 60 s upright starts')
 for seed in (3,17,29):
  subset=[ep for s,ep in raw if s==seed]
  axs[1,0].scatter([seed]*len(subset),[e['tail_x_rms_m']*1000 for e in subset],color=cmap[seed],alpha=.65)
 axs[1,0].set(xticks=[3,17,29],xlabel='Independent optimizer seed',ylabel='Final 5 s cart RMS (mm)',title='Every long episode stayed balanced throughout')
 worst=max(raw,key=lambda r:r[1]['max_abs_x_m']);trace=worst[1]['trajectory']
 axs[1,1].plot([e['t'] for e in trace],[e['theta']*180/np.pi for e in trace],color='#167a74',linewidth=.9)
 axs[1,1].set(xlabel='Time (s)',ylabel='Pole angle (degrees)',title=f"Largest-cart-excursion case: seed {worst[0]}, pose {worst[1]['seed']}")
 for ax in axs.flat:ax.grid(alpha=.15)
 fig.suptitle('Balance retained through PPO; swing-up still unreliable\nNominal encoder model • jerk 150 m/s³ • 100 Hz observed-state policy',fontsize=15)
 fig.supxlabel('*Teacher-only is the initialized baseline (zero PPO decisions). All teacher arms also use supervised pretraining. No hardware qualification.',fontsize=9)
 fig.savefig(a.output/'learning-cycle.png',dpi=160);plt.close(fig)
 print(json.dumps(dict(trials=result['training_trials'],decisions=result['training_decisions'],phases=[(r['method'],r['holds']) for r in summaries])))

if __name__=='__main__':main()
