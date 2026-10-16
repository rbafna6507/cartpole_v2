from pathlib import Path
import hashlib,json,math,statistics
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

base=Path('/home/rbafna/cartpole-v2-runs/retune-20261015')
results=[]
for d in sorted(base.iterdir()):
 try:stamp=int(d.name.rsplit('-',1)[-1])
 except ValueError:continue
 if stamp<1792163890000000000 or not (d/'report.json').exists():continue
 report=json.loads((d/'report.json').read_text())
 if report.get('kind')!='auto' or not report.get('final_info'):continue
 try:
  item=analyze(d)
  b=[s for s in report['states'] if s['mode']==3]
  item['encoder_reference']=report['final_info']['encoder_upright_raw']
  item['i2c_delta']=report['final_info']['i2c_errors']-report['info']['i2c_errors']
  item['mean_balance_x_m']=statistics.mean(s['x'] for s in b) if b else None
  item['mean_balance_angle_deg']=math.degrees(statistics.mean(s['theta'] for s in b)) if b else None
  results.append(item)
 except Exception as e:print('ANALYSIS_ERROR',d.name,repr(e))
results.sort(key=lambda x:int(x['name'].rsplit('-',1)[-1]))
out={'description':'Native encoder-only tuning; jerk150 baseline, two temporary jerk225 comparisons. Original direct reference362; experimental constant trims340/330 are not a validated hanging/nonlinear model. Full raw source logs retained on Jetson.','runs':results}
path=Path('/home/rbafna/cartpole-v2-runs/retune-20261016/session-comparison.json');path.write_text(json.dumps(out,indent=2)+'\n')
for r in results:
 print(json.dumps({k:r[k] for k in ['name','encoder_reference','first_capture_s','observed_longest_balance_s','observed_total_balance_s','mean_balance_x_m','i2c_delta','ok']}))
