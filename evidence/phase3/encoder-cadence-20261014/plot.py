import os
os.environ['MPLCONFIGDIR']='/tmp/cartpole-slow-swing/matplotlib'
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import gzip,json,numpy as np
from pathlib import Path
with gzip.open('/tmp/cartpole-slow-swing/slow.jsonl.gz','rt') as f:
 rows=[r['state'] for line in f if (r:=json.loads(line)).get('type')=='state' and 470626<=r['state']['tick']<=471426]
t=np.array([s['tick']-470626 for s in rows])/1000
fig,ax=plt.subplots(4,1,figsize=(10,8),sharex=True,layout='constrained')
fig.suptitle('Failed swing-up: angle plateaus disrupt control',fontsize=16)
ax[0].step(t,np.unwrap([s['theta'] for s in rows]),where='post',color='#167a94',linewidth=2)
ax[0].set_ylabel('Encoder angle\n(rad, unwrapped)')
ax[0].set_title('100 Hz recorded telemetry; Teensy controller runs at 1 kHz',fontsize=10,loc='left')
ax[1].plot(t,[s['omega'] for s in rows],color='#ad353a');ax[1].set_ylabel('Estimated angular\nvelocity (rad/s)')
ax[2].plot(t,[s['demand'] for s in rows],color='#bb771b',label='Controller request')
ax[2].plot(t,[s['acceleration'] for s in rows],color='#222b45',label='After jerk limiting',linewidth=2)
ax[2].set_ylabel('Acceleration\n(m/s²)');ax[2].legend(loc='upper right',fontsize=9)
ax[3].plot(t,[s['velocity'] for s in rows],color='#222b45',linewidth=2);ax[3].set_ylabel('Commanded cart\nvelocity (m/s)');ax[3].set_xlabel('Time in selected recorded window (s)')
for a in ax:a.grid(alpha=.2);a.spines[['top','right']].set_visible(False)
fig.savefig('/tmp/cartpole-slow-swing/encoder-plateaus.png',dpi=150)
