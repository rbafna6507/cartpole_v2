from pathlib import Path
import sys,json,math

def analyze(directory):
 d=Path(directory);r=json.loads((d/'report.json').read_text());start=r['motion_start']['unwrapped_us'];ss=[]
 for line in next(d.glob('rig-*.jsonl')).read_text().splitlines():
  row=json.loads(line)
  if row['type']=='state' and (not ss or row['state']['unwrapped_us']!=ss[-1]['unwrapped_us']):ss.append(row['state'])
 t=lambda i:(ss[i]['unwrapped_us']-start)/1e6
 ix=[i for i,s in enumerate(ss) if s['mode']==3 and 0<=t(i)];groups=[]
 for i in ix:
  if not groups or i!=groups[-1][-1]+1:groups.append([i])
  else:groups[-1].append(i)
 def metrics(g):
  pairs=[(i,j,t(j)-t(i)) for i,j in zip(g,g[1:]) if 0<t(j)-t(i)<.03]
  if not pairs:return None
  duration=sum(w for i,j,w in pairs)
  avg=lambda fn:sum(w*fn(i,j,w) for i,j,w in pairs)/duration
  return {'duration_observed_s':round(duration,3),'x_mean_m':round(avg(lambda i,j,w:ss[i]['x']),4),'velocity_rms_m_s':round(math.sqrt(avg(lambda i,j,w:ss[i]['velocity']**2)),4),'angle_mean_deg':round(math.degrees(avg(lambda i,j,w:ss[i]['theta'])),3),'angle_rms_deg':round(math.degrees(math.sqrt(avg(lambda i,j,w:ss[i]['theta']**2))),3),'demand_minus_a_rms':round(math.sqrt(avg(lambda i,j,w:(ss[i]['demand']-ss[i]['acceleration'])**2)),3),'jerk_cap_fraction':round(avg(lambda i,j,w:abs(ss[j]['acceleration']-ss[i]['acceleration'])/w>=.95*r['parameters']['jmax']),3),'speed_cap_fraction':round(avg(lambda i,j,w:abs(ss[i]['velocity'])>=.98*min(r['parameters']['vmax'],r['parameters']['vmax_b'])),3),'x_range_m':[round(min(ss[i]['x'] for i in g),4),round(max(ss[i]['x'] for i in g),4)],'max_abs_a':round(max(abs(ss[i]['acceleration']) for i in g),3)}
 episodes=[]
 for g in groups:
  last=g[-1];n=ss[last+1] if last+1<len(ss) else None
  episodes.append({'capture_s':round(t(g[0]),3),'exit_s':round(t(last+1),3) if n else None,'exit_mode':n['mode'] if n else None,'capture':{k:ss[g[0]][k] for k in ('theta','omega','x','velocity','acceleration')},'full':metrics(g),'last_second':metrics([i for i in g if t(i)>t(last)-1]),'first_second':metrics([i for i in g if t(i)<t(g[0])+1])})
 result={'name':d.name,'ok':r['ok'],'parameters':{k:r['parameters'][k] for k in ('pw','pz','pc1','pc2','approach_v','jmax','bw','vmax_b','amax_b')},'hanging_mean_down_angle':r['settling']['mean_down_angle'],'episodes':episodes,'final_fault':r['final']['fault'],'i2c_errors':r['final_info']['i2c_errors']}
 (d/'quick-metrics.json').write_text(json.dumps(result,indent=2)+'\n');return result
if __name__=='__main__':
 for d in sys.argv[1:]:print(json.dumps(analyze(d),indent=2))
