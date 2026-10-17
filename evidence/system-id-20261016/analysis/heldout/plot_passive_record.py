"""Plot raw passive measurements only; no model scoring or fitted alignment."""
import argparse
import gzip
import json
import math
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
d=json.loads(gzip.decompress(a.input.read_bytes()))
s=[dict(zip(d['state_columns'],row)) for row in d['states']]
v=[dict(zip(d['vision_columns'],row)) for row in d['vision']]
origin=s[0]['received_ns']/1e9
t=np.array([row['received_ns']/1e9-origin for row in s])
q=np.array([math.atan2(math.sin(row['theta']-math.pi),math.cos(row['theta']-math.pi)) for row in s])
vt=np.array([row['t']-origin for row in v])
valid=np.array([row.get('pivot_px') is not None and row.get('image_angle_rad') is not None and (row.get('confidence') or 0)>=.5 for row in v])
cq=np.array([-row['image_angle_rad'] if ok else np.nan for row,ok in zip(v,valid)])
pivots=np.array([row['pivot_px'] if ok else [np.nan,np.nan] for row,ok in zip(v,valid)])
pivots-=np.nanmedian(pivots,axis=0)
plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'figure.dpi':150})
fig,axes=plt.subplots(3,1,figsize=(11,7),sharex=True,gridspec_kw={'height_ratios':[2.1,1,1]},layout='constrained')
axes[0].plot(t,np.degrees(q),color='#2269ad',lw=1,label='Raw encoder relative to π')
axes[0].plot(vt,np.degrees(cq),color='#db7622',lw=.8,alpha=.85,label='Raw camera image angle')
axes[0].set_ylabel('Angle from down (°)');axes[0].legend(loc='upper right',ncol=2)
axes[0].set_title('Independent manual validation recording — raw measurements',loc='left',weight='bold')
axes[1].plot(vt,pivots[:,0],'.',ms=1.5,color='#16866a',label='Pivot horizontal')
axes[1].plot(vt,pivots[:,1],'.',ms=1.5,color='#8057a7',label='Pivot vertical')
axes[1].set_ylabel('Pivot displacement\nfrom median (px)');axes[1].legend(loc='upper right',ncol=2)
axes[2].plot(vt,[row.get('confidence') or 0 for row in v],color='#62727f',lw=.7)
axes[2].axhline(.5,color='#b85c5c',ls='--',lw=.7);axes[2].set_ylabel('Tracking confidence');axes[2].set_ylim(-.03,1.05)
axes[2].set_xlabel('Time from first host receipt (s)')
for ax in axes:ax.grid(alpha=.15);ax.set_xlim(0,t[-1])
fig.text(.01,-.025,'Motor disabled throughout. Camera angle is an uncalibrated image projection; timestamps are host proxies. No fitted offsets applied.',fontsize=8,color='#475569')
a.output.parent.mkdir(parents=True,exist_ok=True);fig.savefig(a.output,bbox_inches='tight');plt.close(fig)
print(str(a.output))
