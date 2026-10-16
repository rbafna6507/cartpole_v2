"""Offline JSONL timing audit. Does not import Rig or access any device."""
import sys,json,statistics
from pathlib import Path
p=Path(sys.argv[1]);events=[]
for i,line in enumerate(p.open()):
 try:e=json.loads(line)
 except json.JSONDecodeError:continue
 e['_line']=i+1;events.append(e)
states=[e for e in events if e.get('type')=='state']
errors=[e for e in events if e.get('type')=='error']
if not states:raise SystemExit('No state records')
start=states[0]['state']['received_ns'];stamp=lambda e:e['host_monotonic_ns']
accept=[((stamp(e)-e['state']['received_ns'])/1e6,e) for e in states]
gaps=[((b['state']['received_ns']-a['state']['received_ns'])/1e6,a,b) for a,b in zip(states,states[1:])]
pings=[e for e in events if e.get('type')=='command' and ' PING ' in e.get('payload','')]
pinggaps=[((stamp(b)-stamp(a))/1e6,a,b) for a,b in zip(pings,pings[1:])]
def brief(e):
 s=e.get('state',{});return {'line':e['_line'],'host_s':round((stamp(e)-start)/1e9,6),'kind':e.get('type'),'payload':e.get('payload',e.get('reason')),'tick':s.get('unwrapped_tick',s.get('tick')),'mode':s.get('mode'),'x':s.get('x'),'receipt_s':round((s['received_ns']-start)/1e9,6) if 'received_ns' in s else None,'dropped':s.get('dropped'),'fault':s.get('fault'),'misses':s.get('misses')}
print('COUNTS',json.dumps({'states':len(states),'errors':len(errors),'pings':len(pings)}))
print('ACCEPT_DELAY_MS',json.dumps({'median':statistics.median(v for v,e in accept),'max':max(v for v,e in accept)}))
for v,e in sorted(accept,key=lambda q:q[0],reverse=True)[:8]:print('ACCEPT_MAX',round(v,3),json.dumps(brief(e)))
for v,a,b in sorted(gaps,key=lambda q:q[0],reverse=True)[:8]:print('STATE_GAP',round(v,3),json.dumps(brief(a)),json.dumps(brief(b)))
for v,a,b in sorted(pinggaps,key=lambda q:q[0],reverse=True)[:5]:print('PING_GAP',round(v,3),json.dumps(brief(a)),json.dumps(brief(b)))
for e in errors:
 print('ERROR',json.dumps(brief(e)));near=[q for q in events if stamp(e)-200_000_000<=stamp(q)<=stamp(e)+40_000_000]
 for q in near:print('NEAR',json.dumps(brief(q)))
