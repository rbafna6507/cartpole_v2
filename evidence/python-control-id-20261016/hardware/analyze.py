import json,math,statistics,gzip,sys
from pathlib import Path
root=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parent/'runs';results=[]
for path in sorted(root.glob('*/report.json')):
 r=json.loads(path.read_text())
 # Stationary timing, affinity restoration and characterization reports have
 # separate analyzers; only commission.py reports carry requested_s.
 if r.get('case') not in ('preflight','rehome','zero','auto','native') or 'requested_s' not in r:continue
 log=path.parent/Path(r['log']).name
 data=log.read_text() if log.exists() else gzip.decompress(Path(str(log)+'.gz').read_bytes()).decode()
 rows=[json.loads(line) for line in data.splitlines()]
 states=[row['state'] for row in rows if row['type']=='state'];active=[s for s in states if s['mode']==12 or s['mode'] in (2,3,5,6)]
 transitions=[row for row in rows if row['type']=='policy_transition'];end=[row for row in rows if row['type']=='policy_end']
 s={'case':r['case'],'path':str(path),'failure':r.get('failure'),'bw':r['parameters']['bw'],'rate_hz':r['rate_hz'],'seconds':r['requested_s'],'return_completed':r.get('return_completed'),'final_state':r.get('final_state',r.get('stop_state')),'forecast_mean_us':r.get('forecast_mean_us'),'transitions':transitions,'policy_stats':end,'all_faults':sorted({q['fault'] for q in states})}
 if active:
  start=active[0]['unwrapped_us']*1000;end_ns=active[-1]['unwrapped_us']*1000
  bal=[q for q in transitions if q['mode']=='balance']
  capture=bal[0]['board_ns'] if bal else None
  if r['case']=='native':
   bs=[q for q in active if q['mode']==3];capture=bs[0]['unwrapped_us']*1000 if bs else None
  balanced=[];mode=None;it=iter(transitions);next_t=next(it,None)
  for q in active:
   ns=q['unwrapped_us']*1000
   while next_t is not None and next_t['board_ns']<=ns:mode=next_t['mode'];next_t=next(it,None)
   if (r['case']=='native' and q['mode']==3) or mode=='balance':balanced.append(q)
  s.update(active_s=(end_ns-start)/1e9,first_capture_s=None if capture is None else (capture-start)/1e9,
    balance_samples=len(balanced),theta_rms_deg=None if not balanced else math.sqrt(statistics.mean(q['theta']**2 for q in balanced))*180/math.pi,
    max_abs_x=max(abs(q['x']) for q in active),max_abs_v=max(abs(q['velocity']) for q in active),max_abs_a=max(abs(q['acceleration']) for q in active),
    faults=sorted({q['fault'] for q in active}),misses=active[-1]['misses']-active[0]['misses'],dropped=active[-1]['dropped']-active[0]['dropped'])
 results.append(s)
(root/'summary.json').write_text(json.dumps(results,indent=2))
print(json.dumps([dict(run=Path(s['path']).parent.name,case=s['case'],bw=s['bw'],rate=s['rate_hz'],capture_s=s.get('first_capture_s'),max_x=s.get('max_abs_x'),failure=s['failure']) for s in results],indent=2))
