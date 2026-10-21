#!/usr/bin/env python3
"""Summarize an existing balance failure; no hardware or network access."""
from pathlib import Path
from hashlib import sha256
import argparse,json,math

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--input',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
rows=[json.loads(s) for s in a.input.open()]
failure=next(r for r in rows if r['type']=='policy_failure')
start=next(r for r in rows if r['type']=='policy_start')
states=[r['state'] for r in rows if r['type']=='state']
actions=[r['request'] for r in rows if r['type']=='action_request']
first=next(s for s in states if s['unwrapped_tick']==actions[0]['observation_sequence'])
failed=next(s for s in states if s['unwrapped_tick']==failure['failed_observation_sequence'])
summary=dict(source=str(a.input),source_sha256=sha256(a.input.read_bytes()).hexdigest(),
 script_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),actions=len(actions),
 elapsed_board_ms=(failed['unwrapped_us']-first['unwrapped_us'])/1000.,
 initial_state=first,failed_state=failed,initial_angle_deg=math.degrees(first['theta']),
 failed_angle_deg=math.degrees(failed['theta']),
 last_state=states[-1],crossed_bound=dict(quantity='angular_rate_rad_s',value=failed['omega'],absolute_limit=1.),
 interpretation='Observed rate exceeded wrapper bound. The initial physical pose/true encoder zero and physical cart motion are not independently measured. No proof that calibration offset alone caused the transient.')
(a.output/'report.json').write_text(json.dumps(summary,indent=2)+'\n')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
segment=[s for s in states if first['unwrapped_us']<=s['unwrapped_us']<=states[-1]['unwrapped_us']]
t=[(s['unwrapped_us']-first['unwrapped_us'])/1000 for s in segment]
f,ax=plt.subplots(3,1,figsize=(9,7),sharex=True,layout='constrained')
ax[0].plot(t,[math.degrees(s['theta']) for s in segment],label='Raw encoder angle')
ax[0].axhline(0,color='grey',linestyle=':');ax[0].set_ylabel('Angle (deg)');ax[0].legend()
ax[1].plot(t,[s['omega'] for s in segment],label='Firmware estimated pole speed')
for bound in (-1,1):ax[1].axhline(bound,color='red',linestyle='--')
ax[1].set_ylabel('Rate (rad/s)');ax[1].legend()
ax[2].plot(t,[s['x']*1000 for s in segment],label='Counted cart displacement')
ax[2].set(ylabel='Cart steps (mm)',xlabel='Board time since first action observation (ms)');ax[2].legend()
for pane in ax:pane.axvline(summary['elapsed_board_ms'],color='orange',linestyle=':');pane.grid(alpha=.2)
f.suptitle('Operator balance trial: 7 actions, then pole-speed guard STOP')
f.savefig(a.output/'guard-trip.png',dpi=160);plt.close(f)
print(json.dumps({k:summary[k] for k in ('actions','elapsed_board_ms','initial_angle_deg','failed_angle_deg','crossed_bound')}))
