from pathlib import Path
import gzip,json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
P=Path('/tmp/cartpole-retune-20261015')
r=json.loads(gzip.decompress((P/'upright370-partial.json.gz').read_bytes()))[0]['report'];s=r['states'];compare=json.loads((P/'upright370-camera-comparison.json').read_text())['runs'][0]
cams=json.loads(gzip.decompress((P/'upright370-cameras.json.gz').read_bytes()));cs=next(c['camera'] for c in cams if c['path']==r['path']+'/camera.json')
t=np.array([a['unwrapped_us'] for a in s])/1e6;t=t-t[0];host=np.array([a['received_ns'] for a in s])/1e9;slope=np.polyfit(t,host-host[0],1)[0];base=np.median(host-slope*t)
cs=[c for c in cs if c.get('detected') and c.get('pivot_px') and c.get('bob_px') and c.get('confidence',0)>.7]
ct=(np.array([c['t'] for c in cs])+compare['lag_s']-base)/slope
x=np.array([a['x'] for a in s]);q=np.array([a['theta'] for a in s]);mode=np.array([a['mode'] for a in s]);pv=np.array([c['pivot_px'] for c in cs]);bob=np.array([c['bob_px'] for c in cs]);cq=np.arctan2(bob[:,0]-pv[:,0],pv[:,1]-bob[:,1]);coef=np.polyfit(np.interp(ct,t,x),pv[:,0],1);cx=(pv[:,0]-coef[1])/coef[0]
plt.rcParams.update({'font.size':11,'axes.spines.top':False,'axes.spines.right':False})
fig,ax=plt.subplots(2,1,figsize=(11,6.5),sharex=True)
ax[0].plot(t,x*1000,color='#1e488f',label='Step-count position',lw=1.7);ax[0].scatter(ct,cx*1000,color='#d96324',s=18,label='Camera position (scaled)',zorder=3)
ax[0].axhline(245,color='#b44747',ls='--',lw=1,label='Right braking boundary');ax[0].axhline(0,color='gray',lw=.7)
ax[0].set(ylabel='Cart position (mm)',ylim=(-150,280));ax[0].legend(loc='upper left',ncol=3,fontsize=9)
ax[1].plot(t,np.degrees(q),color='#1e488f',label='Encoder, reference 370',lw=1.5);ax[1].scatter(ct,np.degrees(cq),color='#d96324',s=18,label='Raw camera orientation',zorder=3)
ax[1].axhline(0,color='gray',lw=.7);ax[1].set(ylabel='Angle (degrees)',xlabel='Seconds after auto starts',ylim=(-22,45),xlim=(2.4,3.95));ax[1].legend(loc='upper left',fontsize=9)
start=None
for i,m in enumerate(mode):
 if m==3 and start is None:start=t[i]
 if m!=3 and start is not None:
  for a in ax:a.axvspan(start,t[i],color='#94bc9c',alpha=.18)
  start=None
for a in ax:a.grid(alpha=.18)
fig.suptitle('The cart drifts right during capture; both position sources agree',x=.075,ha='left',fontweight='bold')
fig.text(.075,.025,'Shading: balance mode. Camera aligned by fitted 21.5 ms lag. Raw image angle is not a calibrated gravity reference.',fontsize=9,color='#555')
fig.tight_layout(rect=(0,.05,1,.95));fig.savefig(P/'rightward-drift.png',dpi=160);fig.savefig(P/'rightward-drift.pdf')
