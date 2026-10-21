"""Summarize preserved traces; receipt-to-action times are host proxies, not wire latency."""
from pathlib import Path
import argparse, tempfile
import json, math, tarfile, numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--evidence',type=Path,default=Path(__file__).resolve().parent)
a=parser.parse_args();OUT=a.evidence.resolve()
tmp=tempfile.TemporaryDirectory(prefix='cartpole-policy-analysis-');TEMP=Path(tmp.name).resolve()
for archive in sorted(OUT.glob('live-traces*.tar.gz')):
 with tarfile.open(archive) as tar:
  for member in tar.getmembers():
   target=(TEMP/member.name).resolve()
   if not target.is_relative_to(TEMP) or not (member.isfile() or member.isdir()):raise ValueError('unsafe archive member')
  tar.extractall(TEMP,filter='data')
summary=[]
for p in sorted(TEMP.rglob('report.json')):
 if 'console-policy-20261021' not in p.parts or 'before' not in json.loads(p.read_text()) and not p.parent.name.startswith(('learned','shadow')):continue
 logs=list(p.parent.glob('rig-*.jsonl'))
 if not logs:continue
 report=json.loads(p.read_text());rows=[json.loads(l) for l in logs[0].open()]; states={r['state']['unwrapped_tick']:r['state'] for r in rows if r['type']=='state'}
 actions=[r for r in rows if r['type']=='action_request']; delays=[(r['host_monotonic_ns']-states[r['request']['observation_sequence']]['received_ns'])/1e6 for r in actions]
 active=[r['state'] for r in rows if r['type']=='state' and r['state']['mode']==12]
 item=dict(trial=p.parent.name,success=report.get('success'),error=report.get('error'),actions=len(actions),source=str(logs[0].relative_to(TEMP)))
 if delays:item['receipt_to_request_record_ms']={k:float(v) for k,v in zip(('p50','p99','max'),[np.percentile(delays,50),np.percentile(delays,99),max(delays)])}
 native=[r['state'] for r in rows if r['type']=='state' and r['state']['mode'] in (2,3,5,6)]
 if native:
  dt=float(np.median(np.diff([r['unwrapped_us'] for r in native])))/1e6; best=cur=0
  for state in native:
   cur=cur+1 if state['mode']==3 else 0;best=max(best,cur)
  item.update(native_balance_mode_seconds=sum(r['mode']==3 for r in native)*dt,longest_balance_mode_seconds=best*dt,native_auto_seconds=len(native)*dt,native_max_abs_x_m=max(abs(r['x']) for r in native))
 if active:item.update(observed_position_max_m=max(abs(r['x']) for r in active),observed_angle_rms_rad=float(np.sqrt(np.mean([r['theta']**2 for r in active]))))
 summary.append(item)
(OUT/'trial-summary.json').write_text(json.dumps(dict(semantics='success means requested operation completed, not balance; zero-output tests measure scheduling only; receipt to request record includes host computation and logging timestamps, not verified wire latency',trials=summary),indent=2)+'\n')
p=TEMP/'runs/console-policy-20261021/learned-affinity-02';rows=[json.loads(l) for l in next(p.glob('rig*.jsonl')).open()];s=[r['state'] for r in rows if r['type']=='state' and r['state']['mode']==12];t=np.array([r['unwrapped_us'] for r in s])/1e6;t-=t[0]
fig,axes=plt.subplots(3,1,figsize=(10,7),sharex=True,constrained_layout=True)
axes[0].plot(t,np.degrees([r['theta'] for r in s]),label='Encoder angle');axes[0].axhline(0,color='gray',lw=.7);axes[0].set_ylabel('Angle (degrees)');axes[0].legend(loc='upper right')
axes[1].plot(t,[1000*r['x'] for r in s],color='#d16b24',label='Step-estimated position');axes[1].axhline(-294,color='gray',ls='--',label='Approx. braking boundary');axes[1].axhline(294,color='gray',ls='--');axes[1].set_ylabel('Cart position (mm)');axes[1].legend(loc='upper right')
axes[2].plot(t,[r['demand'] for r in s],alpha=.65,label='Accepted actor demand');axes[2].plot(t,[r['acceleration'] for r in s],label='Governed acceleration');axes[2].set_ylabel('Acceleration (m/s²)');axes[2].set_xlabel('Time since host mode began (s)');axes[2].legend(loc='upper left')
for ax in axes:ax.grid(alpha=.2)
fig.suptitle('Learned balance: timing passed; leftward drift reached rail braking at ~1 s')
fig.savefig(OUT/'learned-trial.png',dpi=160);plt.close(fig)
sel=[r for r in summary if r['trial'] in ('actor-zero-gil5-01','actor-zero-gil1-01','actor-zero-affinity-01','actor-zero-affinity5-01','actor-zero-affinity5-30s-01','learned-affinity-02')]
fig,ax=plt.subplots(figsize=(10,4),constrained_layout=True);labels=[]
for i,r in enumerate(sel):
 d=r['receipt_to_request_record_ms'];ax.plot([d['p50'],d['max']],[i,i],lw=3,color='#158b8d' if r['success'] else '#ce5d3b');ax.scatter([d['p50'],d['p99'],d['max']],[i]*3,s=[20,35,50]);labels.append(r['trial']+f" ({r['actions']} actions)")
ax.set_yticks(range(len(labels)),labels);ax.set_xlabel('Host receipt → action record (ms); max includes faults');ax.grid(axis='x',alpha=.2);ax.set_title('CPU separation reduced observed timing tails\nFinite tests do not establish real-time scheduling guarantees')
fig.savefig(OUT/'timing-comparison.png',dpi=160)
print(json.dumps(summary,indent=2))

plt.close(fig)
tmp.cleanup()
