import json,sys,statistics
from collections import Counter
for path in sys.argv[1:]:
 rows=[];commands=[];infos=[];errors=[]
 for line in open(path):
  try:r=json.loads(line)
  except ValueError:continue
  if r.get('type')=='state':rows.append(r['state'])
  if r.get('type')=='command' and r['payload'].split()[1] not in ('PING','STATUS'):commands.append(r)
  if r.get('type')=='info' or (r.get('type')=='reply' and 'INFO' in r.get('payload','')):infos.append(r)
  if r.get('type')=='error' or (r.get('type')=='reply' and ' ERR ' in r.get('payload','')):errors.append(r)
 segments=[];current=[]
 for s in rows:
  if s['flags']&2:current.append(s)
  elif current:segments.append((current,s));current=[]
 if current:segments.append((current,None))
 result=[]
 for seg,end in segments:
  periods=[];p=seg[0]
  for s in seg[1:]:
   if s['theta']!=p['theta']:periods.append(s['tick']-p['tick']);p=s
  result.append({'first':seg[0],'last':seg[-1],'stopped':end,'samples':len(seg),'duration_s':(seg[-1]['tick']-seg[0]['tick'])/1000,'modes':Counter(s['mode'] for s in seg),'contacts':Counter((s['flags']>>4)&3 for s in seg),'angle_change_periods':Counter(periods).most_common(6),'ranges':{k:[min(s[k] for s in seg),max(s[k] for s in seg)] for k in ('theta','omega','x','velocity','demand','acceleration')}})
 print(json.dumps({'file':path,'commands':commands,'infos':infos,'errors':errors,'segments':result,'last_state':rows[-1] if rows else None},indent=2))
