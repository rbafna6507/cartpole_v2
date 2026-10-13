from pathlib import Path
import json,csv,math
ROOT=Path(__file__).resolve().parents[1]
out=Path(__file__).parent
review=json.loads((ROOT/'analysis/run_reviews/20260916_latest_episodes.json').read_text())[-1]
p=ROOT/'logs/run_20260916_122300.csv'
rows=[{k:float(v) for k,v in r.items()} for r in csv.DictReader(p.open())]
trials=[];seeds=[]
for ep in review['episodes']:
 rs=[r for r in rows if ep['start_board_ms']<=r['t_ms']<ep['end_board_ms']]
 caps=ep['params'];dur=speed=acap=jerk=longest=cur=0
 for a,b in zip(rs,rs[1:]):
  dt=(b['t_ms']-a['t_ms'])*.001;dur+=dt
  near=abs(a['v'])>=.99*caps['vmax'];speed+=dt*near;cur=cur+dt if near else 0;longest=max(longest,cur)
  acap+=dt*(abs(a['accel'])>=.99*caps['amax_s'])
  jerk+=dt*(abs(b['accel']-a['accel'])/dt>=.95*caps['jmax'])
 vals={'trial':ep['trial'],'settings':{k:caps[k] for k in ('vmax','amax_s','amax_b','jmax')},'speed_near_cap_percent':100*speed/dur,'speed_longest_plateau_s':longest,'accel_near_cap_percent':100*acap/dur,'jerk_near_cap_percent':100*jerk/dur,'peak_accel':max(abs(r['accel']) for r in rs)}
 trials.append(vals)
 if ep['trial'] in (2,3,5):
  for a,b in zip(rs,rs[1:]):
   if a['mode']==2 and b['mode']==3:
    seeds.append({'trial':ep['trial'],'board_ms':b['t_ms'],'initialAngle':math.degrees(b['theta']),'initialOmega':b['theta_dot'],'initialX':b['x'],'initialV':b['v'],'initialA':b['accel']})
 print(vals)
(out/'data_informed_cases.json').write_text(json.dumps({'source':review['source'],'snapshot_sha256':review['snapshot_sha256'],'measurement_note':'Capture seeds use raw encoder angle, filtered angular rate and pulse-derived cart state at first BALANCE telemetry sample (up to ~13 ms after handoff), not exact controller state. Jerk saturation estimated from telemetry differences, not per-tick diagnostics.','clipping':trials,'capture_seeds':seeds},indent=2)+'\n')
