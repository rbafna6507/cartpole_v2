#!/usr/bin/env python3
"""Summarize completed console AUTO traces offline; no hardware access."""
import argparse, hashlib, json, math, tarfile
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--input',required=True,type=Path)
 p.add_argument('--output',required=True,type=Path)
 a=p.parse_args()
 if a.input.suffix=='.gz':
  with tarfile.open(a.input,'r:gz') as ar:
   members=[m for m in ar.getmembers() if m.isfile() and m.name.endswith('.jsonl')]
   if len(members)!=1:raise ValueError('exactly one JSONL required')
   raw=ar.extractfile(members[0]).read()
 else:raw=a.input.read_bytes()
 rows=[json.loads(s) for s in raw.splitlines()]
 if not any(r['type']=='termination' for r in rows):raise ValueError('completed recording required')
 states=[r for r in rows if r['type']=='state']
 params={};trials=[]
 for r in rows:
  if r['type']=='parameter':params[r['name']]=r['value']
  if r['type']!='command':continue
  tokens=r['payload'].split()
  if len(tokens)!=5 or tokens[1]!='MODE' or tokens[3]!='auto':continue
  duration=int(tokens[-1])/1000
  eligible=[s['state'] for s in states if s['host_monotonic_ns']>=r['host_monotonic_ns'] and s['state']['flags']&2 and s['state']['mode'] in (2,3,5,6,7,8,9,10,11)]
  if not eligible:continue
  initial=eligible[0]['unwrapped_us']
  segment=[]
  for s in eligible:
   if not 0<=(s['unwrapped_us']-initial)/1e6<=duration:continue
   if segment and s['unwrapped_us']==segment[-1]['unwrapped_us']:
    if any(s[k]!=segment[-1][k] for k in ('theta','x','mode','velocity','fault')):raise ValueError('contradictory duplicate state')
    continue
   segment.append(s)
  t=np.array([(s['unwrapped_us']-initial)/1e6 for s in segment]);dt=np.diff(t)
  if len(t)<2 or np.any(dt<=0):raise ValueError('invalid native time support')
  theta=np.array([s['theta'] for s in segment]);x=np.array([s['x'] for s in segment]);mode=np.array([s['mode'] for s in segment]);v=np.array([s['velocity'] for s in segment])
  good=mode[:-1]==3;streak=longest=0.
  for ok,d in zip(good,dt):
   streak=streak+float(d) if ok else 0.;longest=max(longest,streak)
  tail=(t>=max(0,duration-20))&(mode==3)
  metrics=dict(parameters=dict(params),requested_duration_s=duration,recorded_duration_s=float(t[-1]),samples=len(t),
   balance_mode_total_s=float(dt[good].sum()),balance_mode_longest_s=longest,
   first_balance_s=float(t[np.flatnonzero(mode==3)[0]]) if np.any(mode==3) else None,
   tail_balance_encoder_rms_deg=float(np.rad2deg(np.sqrt(np.mean(theta[tail]**2)))) if np.any(tail) else None,
   tail_balance_counted_cart_mean_m=float(x[tail].mean()) if np.any(tail) else None,
   tail_balance_counted_cart_rms_m=float(np.sqrt(np.mean(x[tail]**2))) if np.any(tail) else None,
   peak_counted_abs_x_m=float(np.max(np.abs(x))),peak_commanded_abs_speed_m_s=float(np.max(np.abs(v))),
   max_board_gap_s=float(dt.max()),faults=sorted({s['fault'] for s in segment}))
  trials.append((metrics,t,theta,x,mode))
 if not trials:raise ValueError('no AUTO trials')
 a.output.mkdir(parents=True,exist_ok=False)
 fig,axes=plt.subplots(3,len(trials),figsize=(6*len(trials),8),squeeze=False,sharex='col',layout='constrained')
 for i,(m,t,theta,x,mode) in enumerate(trials):
  axes[0,i].plot(t,np.rad2deg(theta));axes[0,i].set(title=f"bw={m['parameters']['bw']:g}; native AUTO",ylabel='Encoder angle (deg)')
  axes[1,i].plot(t,x*1000);axes[1,i].set(ylabel='Counted cart (mm)')
  axes[2,i].step(t,mode,where='post');axes[2,i].set(ylabel='Firmware mode (3=balance)',xlabel='Board time (s)')
  for ax in axes[:,i]:ax.grid(alpha=.2)
 fig.savefig(a.output/'native-auto.png',dpi=150);plt.close(fig)
 report=dict(source=str(a.input),source_sha256=hashlib.sha256(raw).hexdigest(),script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
  interpretation='Observed firmware mode, encoder and count/command telemetry only. No independent physical cart or true vertical measurement. Operator-chosen runs, not randomized gain comparison.',trials=[m for m,*_ in trials])
 (a.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
