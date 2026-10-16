from pathlib import Path
import json, math
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
R=Path('/tmp/cartpole-retune-20261016')
rs={p.parent.name:json.loads(p.read_text()) for p in (R/'reports').glob('*/report.json')}
old=next(r for n,r in rs.items() if '-pw3-t1-' in n)
new=next(r for n,r in rs.items() if 'ag5confirm60' in n)
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
f,ax=plt.subplots(3,1,figsize=(11,8),sharex=True)
for r,label,c in [(old,'bw 30: earlier 25 s trial','#ac7860'),(new,'bw 10: 60 s confirmation','#087f8c')]:
 st=r['motion_start']['unwrapped_tick'];rows=[s for s in r['states'] if s['mode']==3 and 0<=(s['unwrapped_tick']-st)/1000<=r['requested_s']]
 t=np.array([(s['unwrapped_tick']-st)/1000 for s in rows]);theta=np.rad2deg([s['theta'] for s in rows]);x=[s['x']*1000 for s in rows]
 ax[0].plot(t,theta,lw=.6,alpha=.85,color=c,label=label)
 ax[1].plot(t,x,lw=.9,color=c)
 edges=np.arange(0,r['requested_s']+2,2)
 rms=[np.sqrt(np.mean(theta[(t>=a)&(t<b)]**2)) if np.any((t>=a)&(t<b)) else np.nan for a,b in zip(edges[:-1],edges[1:])]
 ax[2].plot((edges[:-1]+edges[1:])/2,rms,color=c,lw=1.5)
for a in ax:a.grid(alpha=.18);a.axhline(0,color='#888',lw=.5)
ax[0].set_title('Lower observer bandwidth: less oscillation and a longer hold',loc='left',fontweight='bold',pad=15)
ax[0].set_ylabel('Encoder angle (°)');ax[0].legend(loc='upper right')
ax[1].set_ylabel('Counted cart position (mm)');ax[1].set_ylim(-315,315)
for y in [-294.1,294.1]:ax[1].axhline(y,color='#ad5a47',ls='--',lw=.8)
ax[2].set_ylabel('Angle RMS in 2 s windows (°)');ax[2].set_xlabel('Seconds from AUTO start');ax[2].set_xlim(0,60)
f.text(.07,.016,'Same reference 330, pw 3 and jerk 150 m/s³. Only balance segments shown; both holds end at their scheduled deadline.\nThe 60 s test later stopped during REHOME on stale host telemetry; a separate guarded return succeeded. Angle zero remains experimental.',fontsize=8,color='#444')
f.tight_layout(rect=(0,.055,1,1));f.savefig(R/'filtering-comparison.png',dpi=170);f.savefig(R/'filtering-comparison.svg')
print(R/'filtering-comparison.png')
