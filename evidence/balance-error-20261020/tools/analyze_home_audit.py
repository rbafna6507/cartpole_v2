#!/usr/bin/env python3
"""Offline endpoint/count audit; no hardware access."""
import argparse,hashlib,json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--input',type=Path,required=True)
 p.add_argument('--output',type=Path,required=True)
 a=p.parse_args()
 report=json.loads((a.input/'report.json').read_text())
 sources=list((a.input/'raw').glob('*.jsonl'))
 if len(sources)!=1:raise ValueError('exactly one raw log required')
 raw=sources[0].read_bytes();rows=[json.loads(s) for s in raw.splitlines()]
 if rows[-1].get('type')!='termination' or rows[-1].get('records_dropped')!=0 or rows[-1].get('error') is not None:
  raise ValueError('clean complete log required')
 if not report['completed'] or not report['stop_confirmed']:raise ValueError('completed stopped HOME required')
 states=[]
 for r in rows:
  if r['type']!='state':continue
  s=r['state']
  if states and s['unwrapped_us']==states[-1]['unwrapped_us']:continue
  states.append(s)
 origin=states[0]['unwrapped_us']; result={}
 steps_per_m=26666.6666667
 old_half_steps=report['before']['info']['measured_span_steps']//2
 for name,bit,sign in [('left',16,-1),('right',32,1)]:
  contacts=[s for s in states if s['mode']==13 and s['flags']&bit]
  stationary=[s for s in contacts if s['velocity']==0]
  if not stationary:raise ValueError(f'no stationary contact for {name}')
  last=stationary[-1]['x'];expected=sign*old_half_steps/steps_per_m
  result[name]={'last_stationary_contact_old_coordinate_m':last,'old_expected_coordinate_m':expected,
   'difference_mm':(last-expected)*1000,'contact_coordinate_range_m':[min(s['x'] for s in contacts),max(s['x'] for s in contacts)]}
 result.update({'before_span_steps':report['before']['info']['measured_span_steps'],
  'after_span_steps':report['after']['info']['measured_span_steps'],
  'nominal_step_scale_m_per_step':1/steps_per_m,
  'home_epoch':report['after']['info']['home_epoch'],
  'reference':report['after']['info']['encoder_upright_raw'],
  'parameter_changes':report['parameter_changes'],'raw_sha256':hashlib.sha256(raw).hexdigest(),
  'interpretation':'Final switch contact coordinates repeat at logged resolution. This single audit shows no net endpoint/count discrepancy; it does not establish metric accuracy, transient actuator lag or absence of canceling missed steps.'})
 a.output.mkdir(parents=True,exist_ok=False)
 (a.output/'report.json').write_text(json.dumps(result,indent=2)+'\n')
 fig,axs=plt.subplots(2,1,figsize=(10,6),sharex=True,layout='constrained')
 t=[(s['unwrapped_us']-origin)/1e6 for s in states]
 axs[0].plot(t,[s['x']*1000 for s in states]);axs[0].set(ylabel='Counted cart position (mm)',title='Native two-switch HOME; coordinates repeat')
 for name,bit,c in [('Left',16,'tab:orange'),('Right',32,'tab:green')]:
  contacts=[s for s in states if s['mode']==13 and s['flags']&bit]
  axs[0].scatter([(s['unwrapped_us']-origin)/1e6 for s in contacts],[s['x']*1000 for s in contacts],s=20,c=c,label=name+' contact')
 axs[0].legend()
 axs[1].plot(t,[s['velocity'] for s in states]);axs[1].set(ylabel='Commanded velocity (m/s)',xlabel='Board time (s)')
 for ax in axs:ax.grid(alpha=.2)
 fig.savefig(a.output/'home-audit.png',dpi=140);plt.close(fig)
 print(json.dumps(result,indent=2))
if __name__=='__main__':main()
