"""Read-only quick metrics for one native AUTO trial; board modes are not physical balance proof."""
import argparse,json,math,statistics
from pathlib import Path

def stats(v):
 return None if not v else dict(n=len(v),mean=statistics.mean(v),rms=math.sqrt(statistics.mean(x*x for x in v)),minimum=min(v),maximum=max(v))

def score(path):
 rows=[]
 for f in sorted(path.glob('rig*.jsonl')):
  for line in f.read_text().splitlines():
   try:r=json.loads(line)
   except json.JSONDecodeError:continue
   if r.get('type')=='state':rows.append(r['state'])
 s=sorted({r['unwrapped_us']:r for r in rows}.values(),key=lambda r:r['unwrapped_us'])
 if not s:raise ValueError('No telemetry')
 if len({r['sid'] for r in s})!=1:raise ValueError('Expected one direct rig session')
 active=[r for r in s if r['mode'] in (2,3,5,6,7,8,9,10,11)]
 first=active[0]['unwrapped_us'] if active else None
 holds=[];current=[]
 for r in s:
  if r['mode']==3:
   if current and r['unwrapped_us']-current[-1]['unwrapped_us']>30000:holds.append(current);current=[]
   current.append(r)
  elif current:holds.append(current);current=[]
 if current:holds.append(current)
 duration=lambda h:(h[-1]['unwrapped_us']-h[0]['unwrapped_us'])/1e6
 longest=max(holds,key=duration,default=[])
 stable=[r for r in longest if r['unwrapped_us']-longest[0]['unwrapped_us']>=2000000]
 p=path/'report.json';report=json.loads(p.read_text()) if p.exists() else {}
 return dict(trial=path.name,collector_complete=p.exists(),collector_success=report.get('success'),collector_error=report.get('error'),
  first_capture_s=None if not holds or first is None else (holds[0][0]['unwrapped_us']-first)/1e6,
  longest_BAL_s=duration(longest) if longest else 0.,total_BAL_s=sum(duration(h) for h in holds),BAL_entries=len(holds),
  mode_counts={str(m):sum(r['mode']==m for r in s) for m in sorted({r['mode'] for r in s})},
  active_cart_m=stats([r['x'] for r in active]),active_acceleration_m_s2=stats([r['acceleration'] for r in active]),
  settled_longest_hold=dict(angle_deg=stats([math.degrees(r['theta']) for r in stable]),omega_rad_s=stats([r['omega'] for r in stable]),cart_m=stats([r['x'] for r in stable]),commanded_velocity_m_s=stats([r['velocity'] for r in stable]),acceleration_m_s2=stats([r['acceleration'] for r in stable])),
  balance_transitions=[dict(t_s=(h[0]['unwrapped_us']-first)/1e6,duration_s=duration(h),entry={k:h[0][k] for k in ('theta','omega','x','velocity','acceleration')},exit={k:h[-1][k] for k in ('theta','omega','x','velocity','acceleration')}) for h in holds],
  test_parameters=report.get('test_parameters'),after=report.get('after'),info_after=report.get('info_after'),
  interpretation='Mode3 interval duration; gaps>30ms break intervals. Settled metrics use longest interval after2s. Cart position is step-counted and velocity commanded, not physical metrology.')

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('path',type=Path);a=p.parse_args();print(json.dumps(score(a.path),indent=2,allow_nan=False))
