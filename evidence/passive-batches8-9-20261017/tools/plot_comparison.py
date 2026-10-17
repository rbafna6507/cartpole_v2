#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=1.26,<3", "matplotlib>=3.8,<4"]
# ///
"""Plot all saved frozen-evaluation releases; never fit or select intervals."""
import argparse,gzip,json,math
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--title',required=True);a=p.parse_args()
if a.output.exists():raise FileExistsError(a.output)
r=json.loads(gzip.decompress(a.report.read_bytes()))
old=next(x for x in r['results'] if x['model']=='weak_viscous' and x['initializer']!='original')['metrics']['continuous_after_history'][1]
new=next(x for x in r['results'] if x['model']=='weak_coulomb')['metrics']['continuous_after_history'][1]
base=r['source_identity']['passive_baseline']['encoder']['raw_angle_rad']
fig,axes=plt.subplots(math.ceil(len(new['episodes'])/3),3,figsize=(15,3.4*math.ceil(len(new['episodes'])/3)),layout='constrained',squeeze=False)
for ax,o,n in zip(axes.flat,old['episodes'],new['episodes']):
 t=np.array(n['t']);q=np.array(n['observed']);branch=base+2*np.pi*round((np.median(q)-base)/(2*np.pi));t=t-t[0]
 ax.plot(t,np.rad2deg(q-branch),c='#1766a0',lw=1.1,label='Recorded encoder')
 ax.plot(t,np.rad2deg(np.array(o['predicted'])-branch),c='#888888',lw=1,label='Earlier viscous')
 ax.plot(t,np.rad2deg(np.array(n['predicted'])-branch),c='#d56720',lw=1.1,label='Frozen batch-6 friction')
 ax.set_title(f"{n['episode_id']}: {o['metrics']['rms_deg']:.2f}° → {n['metrics']['rms_deg']:.2f}° RMS")
 ax.set_xlabel('Seconds after prediction starts');ax.set_ylabel('Angle from recorded hanging (°)');ax.grid(alpha=.2)
for ax in list(axes.flat)[len(new['episodes']):]:ax.set_visible(False)
axes.flat[0].legend(fontsize=8)
fig.suptitle(f"{a.title}: all frozen release intervals\nFirst 0.5 s initializes state; no later observations. Aggregate RMS {old['metrics']['rms_deg']:.2f}° → {new['metrics']['rms_deg']:.2f}°\nNo refit; camera/pose flags remain separate; DEVELOPMENT_ONLY",fontsize=13)
fig.savefig(a.output,dpi=140);plt.close(fig)
