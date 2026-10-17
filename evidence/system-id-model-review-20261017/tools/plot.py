#!/usr/bin/env python3
"""Plot saved evidence only, without fitting or model promotion."""
import argparse,gzip,json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
p=argparse.ArgumentParser();p.add_argument('--report',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
if a.output.exists():raise FileExistsError(a.output)
r=json.loads(gzip.decompress(a.report.read_bytes()));old=next(x for x in r['results'] if x['model']=='weak_viscous' and x['initializer']!='original');new=next(x for x in r['results'] if x['model']=='weak_coulomb');role='validation'
old=old['results'][role]['continuous_after_history'][1];new=new['results'][role]['continuous_after_history'][1]
fig,axes=plt.subplots(3,2,figsize=(13,10),layout='constrained')
for ax,o,n in zip(axes.flat,old['episodes'],new['episodes']):
 t=np.array(n['t']);q=np.array(n['observed']);branch=np.pi+2*np.pi*round((np.median(q)-np.pi)/(2*np.pi));t=t-t[0]
 ax.plot(t,np.rad2deg(q-branch),c='#1766a0',lw=1.1,label='Recorded encoder')
 ax.plot(t,np.rad2deg(np.array(o['predicted'])-branch),c='#888888',lw=1,alpha=.8,label='Viscous model')
 ax.plot(t,np.rad2deg(np.array(n['predicted'])-branch),c='#d56720',lw=1.1,label='Viscous + dry friction')
 ax.set_title(f"{n['episode_id']}: {o['metrics']['rms_deg']:.2f}° → {n['metrics']['rms_deg']:.2f}° RMS")
 ax.set_xlabel('Seconds after prediction starts');ax.set_ylabel('Raw encoder angle − hanging branch (°)');ax.grid(alpha=.2)
axes.flat[0].legend(fontsize=8)
fig.suptitle(f"Batch 5 development: uninterrupted predictions, equal starting procedure\nFirst 0.5 s initializes state; no later observations. Aggregate RMS {old['metrics']['rms_deg']:.2f}° → {new['metrics']['rms_deg']:.2f}°\nTraining-only coefficients; no simulator export or final holdout acceptance",fontsize=13)
a.output.parent.mkdir(parents=True,exist_ok=True);fig.savefig(a.output,dpi=150);plt.close(fig)
