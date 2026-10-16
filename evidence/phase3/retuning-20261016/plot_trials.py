from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
ROOT=Path('/tmp/cartpole-retune-20261016')
reports=[]
for d in (ROOT/'reports').iterdir():
 p=d/'report.json'
 if p.exists():
  r=json.loads(p.read_text())
  if r.get('final_info',{}).get('encoder_upright_raw')==330 and r.get('motion_start'):
   r['name']=d.name;reports.append(r)
reports.sort(key=lambda r:int(r['name'].rsplit('-',1)[1]))
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
fig,ax=plt.subplots(figsize=(11,max(5,.38*len(reports)+1.7)))
for row,r in enumerate(reports):
 states=r['states'];start=r['motion_start']['unwrapped_tick'];data=[s for s in states if 0<=(s['unwrapped_tick']-start)/1000<=r['requested_s']+.01]
 ax.broken_barh([(0,r['requested_s'])],(row-.32,.64),facecolors='#e4e8ec')
 for mode,color in [(3,'#167a72'),(5,'#df9358'),(6,'#df9358')]:
  inds=np.array([i for i,s in enumerate(data) if s['mode']==mode]);groups=np.split(inds,np.flatnonzero(np.diff(inds)>1)+1)
  for group in groups:
   if not len(group):continue
   lo=(data[group[0]]['unwrapped_tick']-start)/1000;hi=(data[group[-1]]['unwrapped_tick']-start)/1000
   ax.broken_barh([(lo,hi-lo+.004)],(row-.32,.64),facecolors=color)
 labels=[]
for r in reports:
 name=r['name'].rsplit('-',1)[0].replace('reference330-','');labels.append(name)
ax.set_yticks(range(len(reports)),labels);ax.invert_yaxis();ax.set_xlim(0,60.5);ax.set_xticks(range(0,61,5));ax.grid(axis='x',alpha=.18);ax.set_xlabel('Seconds from AUTO start; gray = swing-up, green = balance, orange = rail recovery')
ax.set_title('Longer trials reveal both capture failures and sustained holds',loc='left',fontweight='bold',pad=18)
fig.text(.02,.012,'Encoder-only native control at 1 kHz; telemetry 250 Hz. Reference 330 is an experimental constant trim. A green bar reaching the deadline is a censored hold.',fontsize=8,color='#444')
fig.tight_layout(rect=(0,.035,1,1));fig.savefig(ROOT/'trial-timeline.png',dpi=160);fig.savefig(ROOT/'trial-timeline.svg');plt.close(fig)
fig,axs=plt.subplots(2,1,figsize=(10,6),sharex=True)
for prefix,color in [('reference330-pw3-t1','#167a72'),('reference330-pw3-t2','#b56b34')]:
 r=next(r for r in reports if r['name'].startswith(prefix));b=[s for s in r['states'] if s['mode']==3];t=(np.array([s['unwrapped_tick'] for s in b])-b[0]['unwrapped_tick'])/1000
 axs[0].plot(t,np.rad2deg([s['theta'] for s in b]),lw=.7,alpha=.8,color=color,label=prefix.rsplit('-',1)[1])
 axs[1].plot(t,[s['x'] for s in b],lw=1,color=color)
for ax in axs:ax.grid(alpha=.18);ax.axhline(0,color='#777',lw=.5)
axs[0].set_ylabel('Encoder angle (degrees)');axs[0].legend(title='Unchanged repeats',loc='upper right');axs[0].set_title('pw = 3: two full-duration holds, with residual oscillation',loc='left',fontweight='bold')
axs[1].set_ylabel('Counted cart position (m)');axs[1].set_xlabel('Seconds since capture');axs[1].axhline(.294,color='#b45638',ls='--',lw=.8);axs[1].axhline(-.294,color='#b45638',ls='--',lw=.8);axs[1].set_ylim(-.315,.315)
fig.text(.02,.012,'Both traces ended at the scheduled 25-second AUTO deadline. Position is step count, not an independent physical measurement. The third repeat failed at capture.',fontsize=8,color='#444')
fig.tight_layout(rect=(0,.035,1,1));fig.savefig(ROOT/'pw3-holds.png',dpi=160);fig.savefig(ROOT/'pw3-holds.svg')
print('plotted',len(reports),'trials')
