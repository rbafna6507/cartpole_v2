from pathlib import Path
import argparse,hashlib,json,math
p=argparse.ArgumentParser();p.add_argument('directories',nargs='+');p.add_argument('--output',required=True);a=p.parse_args()
def analyze(d):
 report=json.loads((d/'report.json').read_text()); states=[]
 for line in next(d.glob('rig-*.jsonl')).read_text().splitlines():
  event=json.loads(line)
  if event['type']=='state':
   s=event['state']
   if not states or s['unwrapped_us']!=states[-1]['unwrapped_us']:states.append(s)
 start=report['motion_start']['unwrapped_us']; t=lambda s:(s['unwrapped_us']-start)/1e6
 horizon=report['requested_s']; episodes=[]; group=[]
 for i,s in enumerate(states):
  if s['mode']==3 and 0<=t(s)<=horizon+.01:
   if group and (i!=group[-1]+1 or t(s)-t(states[group[-1]])>.03):episodes.append(group);group=[]
   group.append(i)
  elif group:episodes.append(group);group=[]
 if group:episodes.append(group)
 details=[]
 for group in episodes:
  first,last=group[0],group[-1];f,l=states[first],states[last];n=states[last+1] if last+1<len(states) else None
  details.append({'entry_bracket_s':[t(states[first-1]),t(f)],'exit_bracket_s':[t(l),t(n) if n else None],
   'observed_duration_s':t(l)-t(f),'duration_upper_s':(t(n)-t(states[first-1])) if n else None,
   'exit_mode':n['mode'] if n else None,'exit_x_m':n['x'] if n else None,'exit_velocity_m_s':n['velocity'] if n else None,
   'entry_x_m':f['x'],'entry_velocity_m_s':f['velocity'],
   'angle_rms_deg':math.degrees(math.sqrt(sum(states[j]['theta']**2 for j in group)/len(group)))})
 active=[s for s in states if 0<=t(s)<=horizon+.01]
 transitions=[{'t':t(s),'from':states[i-1]['mode'],'to':s['mode'],'x':s['x'],'v':s['velocity'],'a':s['acceleration'],'theta':s['theta'],'brake_direction':s['brake_direction']} for i,s in enumerate(states) if i and s['mode']!=states[i-1]['mode'] and 0<=t(s)<=horizon+.05]
 return {'name':d.name,'ok':report['ok'],'requested_s':horizon,'jmax':report['parameters']['jmax'],'parameters':report['parameters'],'settling':report.get('settling'),
  'first_capture_s':details[0]['entry_bracket_s'][1] if details else None,'episodes':details,
  'observed_total_balance_s':sum(e['observed_duration_s'] for e in details),'observed_longest_balance_s':max((e['observed_duration_s'] for e in details),default=0),
  'balance_exits_to_rail':sum(e['exit_mode']==5 for e in details),'rail_recovery_entries':sum(t['to']==5 for t in transitions),
  'max_abs_x_m':max(abs(s['x']) for s in active),'max_abs_v_m_s':max(abs(s['velocity']) for s in active),
  'transitions':transitions,'camera_return_delta_px':report.get('camera_return_delta_px'),'final':report['final'],'final_info':report['final_info'],
  'sha256':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in [d/'report.json',d/'camera.json',next(d.glob('rig-*.jsonl'))]}}
results=[analyze(Path(d)) for d in a.directories]
out={'schema':'preflash-repeat-comparison-v1','timing':'Board microsecond timestamps relative to last settled observation before MODE command. Entry/exit brackets reflect telemetry sampling. Observed episode duration is a conservative lower bound; mode is not an independent physical balance measurement.','script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'runs':results}
Path(a.output).write_text(json.dumps(out,indent=2)+'\n')
for r in results:
 print(json.dumps({k:r[k] for k in ['name','jmax','first_capture_s','observed_total_balance_s','observed_longest_balance_s','balance_exits_to_rail','rail_recovery_entries','max_abs_x_m','camera_return_delta_px','episodes']},indent=2))
