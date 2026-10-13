"""Offline full-rate plots. Usage: uv run --with matplotlib plot_session.py SESSION/angles.csv"""
import argparse,csv
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
p=argparse.ArgumentParser();p.add_argument('csv');a=p.parse_args()
with open(a.csv) as f:rows=list(csv.DictReader(f))
if not rows:raise SystemExit('CSV contains no samples')
def nums(key):return np.array([float(r[key]) if r.get(key) not in (None,'','None') else np.nan for r in rows])
t=nums('host_read_s');t-=t[0];theta=np.rad2deg(nums('theta_down_rad'));x=nums('cart_x_mm')
theta[[r['valid'].lower() not in ('true','1') for r in rows]]=np.nan
x[[r.get('cart_valid','false').lower() not in ('true','1') for r in rows]]=np.nan
# Do not draw through capture gaps or angle wrap boundaries.
gaps=np.r_[False,np.diff(t)>.1];wraps=np.r_[False,np.abs(np.diff(theta))>180];theta[gaps|wraps]=np.nan;x[gaps]=np.nan
# Calibration changes can redefine zero/scale; break the trace at each event.
events=Path(a.csv).with_name('calibration_events.jsonl')
if events.exists():
 import json
 absolute_start=float(rows[0]['host_read_s'])
 for line in events.read_text().splitlines():
  event=json.loads(line);idx=np.searchsorted(t,event['t']-absolute_start)
  if 0<=idx<len(t):theta[idx]=np.nan;x[idx]=np.nan
fig,axes=plt.subplots(4,1,sharex=True,figsize=(11,10));axes[0].plot(t,theta,lw=.8);axes[0].set_ylabel('Theta from down (deg)');axes[1].plot(t,x,lw=.8);axes[1].set(ylabel='Cart from midpoint (mm)',xlabel='Time since first frame read (s)')
for ax,key,label in [(axes[2],'cart_v_mm_s','Cart velocity (mm/s)'),(axes[3],'cart_a_mm_s2','Cart acceleration (mm/s²)')]:
 values=nums(key);values[gaps]=np.nan;ax.plot(t,values,lw=.8);ax.set_ylabel(label)
axes[3].set_xlabel('Time since first frame read (s)')
for ax in axes:ax.grid(alpha=.25)
fig.tight_layout();out=Path(a.csv).with_name('position_theta.png');fig.savefig(out,dpi=160);print(out)
