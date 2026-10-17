#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["matplotlib>=3.8,<4", "numpy>=1.26,<3"]
# ///
"""Plot all optimizer seeds from frozen diagnostic reports; no fitting or training."""
import argparse,json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('pilots',nargs='+',type=Path)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args()
reports=[json.loads((path/'report.json').read_text()) for path in a.pilots]
colors={'upright':'#546e7a','upright-lowstd':'#006d77','upright-scaled':'#b65c24','mixed':'#6b4ca5'}
fig,axs=plt.subplots(2,2,figsize=(12,8),layout='constrained')
for variant in sorted({r['variant'] for r in reports}):
 group=[r for r in reports if r['variant']==variant]
 for ax,metric,title in zip(axs.flat,['balanced_fraction','longest_balance_dwell_s','score','raw_action_delta_rms'],['Time balanced (fraction)','Longest continuous balance (s)','Raw benchmark score','Raw action change RMS (m/s² per decision)']):
  curves=[]
  for r in group:
   x=np.array([e['steps'] for e in r['evaluations']])/1000
   y=[e['by_start']['upright'][metric] for e in r['evaluations']]
   curves.append(y)
   ax.plot(x,y,color=colors[variant],alpha=.3,lw=1,marker='.',ms=4)
  if len({len(y) for y in curves})==1:
   ax.plot(x,np.median(curves,axis=0),color=colors[variant],label=variant,lw=2.3,marker='o',ms=4)
  ax.set(title=title,xlabel='Training decisions (thousands)')
  ax.grid(alpha=.2)
axs[0,0].set_ylim(0,1.02)
axs[0,0].legend(fontsize=9)
fig.suptitle('Short balance-learning screen · thin lines: every optimizer seed · bold: median\nNominal encoder model; 5 s training, 10 s development evaluation; not a convergence proof',fontsize=12)
a.output.parent.mkdir(parents=True,exist_ok=True)
fig.savefig(a.output,dpi=160)
print(a.output)
