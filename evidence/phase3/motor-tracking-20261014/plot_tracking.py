import os
os.environ['MPLCONFIGDIR']='/tmp/cartpole-slow-swing/matplotlib'
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import json,numpy as np,gzip
from pathlib import Path
root=Path('/tmp/cartpole-slow-swing')
d=json.loads((root/'first-auto-aligned.json').read_text());rows=d['rows'];t=[r['t'] for r in rows]
rt=[];rx=[];rv=[];ra=[]
for l in gzip.open(root/'latest-rig.jsonl.gz','rt'):
 r=json.loads(l)
 if r.get('type')!='state':continue
 s=r['state'];tt=s['received_ns']/1e9-93527.554935
 if -.25<=tt<=4.25:rt.append(tt);rx.append(s['x']*1000);rv.append(s['velocity']);ra.append(s['acceleration'])
fig,ax=plt.subplots(3,1,figsize=(10,7.5),sharex=True,layout='constrained')
fig.suptitle('Cart stops tracking during the first failed auto run',fontsize=16)
ax[0].plot(rt,rx,color='#263653',label='Position inferred from emitted steps')
ax[0].plot(t,[(r['px']-rows[0]['px'])/d['fit'][0]*1000 for r in rows],color='#d56529',marker='.',label='Camera pivot displacement (approximate scale)')
ax[0].set_ylabel('Displacement (mm)');ax[0].legend(fontsize=9,loc='lower right')
ax[1].plot(rt,rv,color='#263653');ax[1].set_ylabel('Commanded speed\n(m/s)')
ax[2].plot(rt,ra,color='#263653');ax[2].set_ylabel('Governed acceleration\n(m/s²)');ax[2].set_xlabel('Time from auto start (s)')
for a in ax:a.grid(alpha=.2);a.spines[['top','right']].set_visible(False);a.axvline(0,color='grey',linestyle=':');a.axvline(3.93,color='grey',linestyle=':')
fig.text(.01,.002,'Camera scale fitted to the slow homing pass; host timestamps, uncalibrated camera delay. No motor current or shaft measurement.',fontsize=8,color='#555')
fig.savefig(root/'motor-tracking.png',dpi=160)
