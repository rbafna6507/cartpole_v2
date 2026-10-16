#!/usr/bin/env python3
"""Offline native-board-time comparison. No hardware or production imports."""
from pathlib import Path
import json, math, hashlib, tarfile, argparse
import numpy as np
R=180/np.pi;ANCHOR=-0.009445365634260372
wrap=lambda v:(np.asarray(v)+np.pi)%(2*np.pi)-np.pi

def quant(values,weights,ps=(.5,.95,.99)):
 a=np.asarray(values);w=np.asarray(weights);ok=np.isfinite(a)&(w>0);a=a[ok];w=w[ok]
 if not len(a):return [None for _ in ps]
 i=np.argsort(a);return np.interp(np.asarray(ps)*sum(w),np.cumsum(w[i]),a[i]).tolist()
def stats(v,w):
 v=np.asarray(v);w=np.asarray(w);keep=w>0;v=v[keep];w=w[keep]
 if not len(v):return {'duration_s':0,'n':0}
 return dict(duration_s=float(sum(w)),n=len(v),rms=float(np.sqrt(np.average(v*v,weights=w))),mean=float(np.average(v,weights=w)),abs_quantiles_p50_p95_p99=quant(abs(v),w),max_abs=float(max(abs(v))))
def episodes(t,m,value,low,high,gap=.030):
 rows=[];ix=np.where((t>=low)&(t<=high)&(m==value))[0];groups=[]
 for i in ix:
  if not groups or i!=groups[-1][-1]+1 or t[i]-t[i-1]>gap:groups.append([i])
  else:groups[-1].append(i)
 for g in groups:
  a,b=g[0],g[-1];prev=max(low,t[a-1]) if a else low;nxt=min(high,t[b+1]) if b+1<len(t) else high
  rows.append(dict(first_s=float(t[a]-low),last_s=float(t[b]-low),lower_duration_s=float(t[b]-t[a]),upper_duration_s=float(nxt-prev),entry_interval_s=[float(prev-low),float(t[a]-low)],exit_interval_s=[float(t[b]-low),float(nxt-low)],samples=len(g),index_first=int(a),index_last=int(b)))
 return rows

def analyze(d):
 report=json.loads((d/'report.json').read_text());cam=json.loads((d/'camera.json').read_text());log=next(d.glob('rig-*.jsonl'));events=[json.loads(l) for l in log.read_text().splitlines()];allstates=[e['state'] for e in events if e['type']=='state'];ss=[];dup=0
 for s in allstates:
  if ss and s['unwrapped_us']==ss[-1]['unwrapped_us']:
   dup+=1
   if s['theta']!=ss[-1]['theta']:raise ValueError('duplicate board tick with changed raw theta')
   continue
  ss.append(s)
 t=np.array([s['unwrapped_us']/1e6 for s in ss]);assert np.all(np.diff(t)>0)
 low=report['motion_start']['unwrapped_us']/1e6;high=low+report['requested_s'];tt=t-low;m=np.array([s['mode'] for s in ss]);healthy=np.array([bool(s['flags']&1) and s['fault']==0 for s in ss]);a=np.array([s['acceleration'] for s in ss]);demand=np.array([s['demand'] for s in ss]);v=np.array([s['velocity'] for s in ss]);x=np.array([s['x'] for s in ss]);th=np.array([s['theta'] for s in ss]);om=np.array([s['omega'] for s in ss]);br=np.array([s['brake_direction'] for s in ss]);dt=np.diff(t)
 weights=np.maximum(0,np.minimum(t[1:],high)-np.maximum(t[:-1],low));weights[dt>.030]=0;active=(tt>=0)&(tt<=report['requested_s']);jerk=np.diff(a)/dt;dslew=np.diff(demand)/dt;jmax=report['parameters']['jmax']
 result={'name':d.name,'parameters':{k:report['parameters'][k] for k in ['pw','bw','jmax','bal_pw','vmax','amax_s','amax_b','catch_da']},'reference_raw':report['info']['encoder_upright_raw'],'reported_success':report['ok'],'source_hashes':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in [d/'report.json',d/'camera.json',log]},'time':{'board_window_start_s':low,'board_window_end_s':high,'source_state_n':len(allstates),'deduplicated_n':len(ss),'duplicate_tick_n':dup,'covered_interval_s':float(sum(weights)),'active_gap_ms_p50_p95_max':np.percentile(dt[weights>0]*1000,[50,95,100]).tolist(),'health_invalid_n':int(sum(~healthy[active]))},'mode_duration_left_hold_s':{str(k):float(sum(weights[m[:-1]==k])) for k in sorted(set(m[active]))}}
 for mode,name in [(3,'balance'),(5,'rail_brake'),(6,'rail_return')]:
  eps=episodes(t,m,mode,low,high)
  for e in eps:
   ix=np.arange(e.pop('index_first'),e.pop('index_last')+1);e['max_abs_theta_deg']=float(max(abs(th[ix]))*R);e['start_x']=float(x[ix[0]]);e['exit_x']=float(x[ix[-1]]);e['max_abs_x']=float(max(abs(x[ix])));e['last_100ms_demand_minus_accel_max_abs']=float(max(abs((demand-a)[ix[t[ix]>=t[ix[-1]]-.1]])));e['end_mode_next']=int(m[ix[-1]+1]) if ix[-1]+1<len(m) else None
  result[name]={'episodes':eps,'count':len(eps),'total_lower_duration_s':sum(e['lower_duration_s'] for e in eps),'total_upper_duration_s':sum(e['upper_duration_s'] for e in eps),'longest_lower_s':max([e['lower_duration_s'] for e in eps] or [0])}
 result['first_capture_board_s']=result['balance']['episodes'][0]['entry_interval_s'] if result['balance']['episodes'] else None
 result['limits']={'max_abs_x_m':float(max(abs(x[active]))),'max_abs_v_m_s':float(max(abs(v[active]))),'max_abs_accel_m_s2':float(max(abs(a[active]))),'max_abs_demand_m_s2':float(max(abs(demand[active]))),'max_abs_omega_rad_s':float(max(abs(om[active])))}
 result['actuation']={}
 for key,mask in [('swing',m[:-1]==2),('balance',m[:-1]==3),('balance_away_from_rail_speed_limit',(m[:-1]==3)&(br[:-1]==0)&(abs(x[:-1])<.20)&(abs(v[:-1])<1.2)),('swing_balance',np.isin(m[:-1],[2,3])),('swing_balance_away_from_rail_speed_limit',np.isin(m[:-1],[2,3])&(br[:-1]==0)&(abs(x[:-1])<.20)&(abs(v[:-1])<1.2))]:
  w=weights*mask;wi=w*(m[:-1]==m[1:])*(br[:-1]==0)*(br[1:]==0);den=float(sum(wi));res=demand[:-1]-a[:-1]
  result['actuation'][key]={'demand_minus_acceleration':stats(res,w),'theta_deg':stats(th[:-1]*R,w),'demand':stats(demand[:-1],w),'acceleration':stats(a[:-1],w),'residual_abs_gt4_time_fraction':float(sum(w*(abs(res)>4))/sum(w)) if sum(w) else None,'jerk_interval_eligible_s':den,'observed_avg_abs_jerk_p50_p95_p99':quant(abs(jerk),wi),'observed_avg_jerk_near150_fraction':float(sum(wi*(abs(jerk)>=.95*jmax))/den) if den else None,'jerk_near150_and_toward_demand_fraction':float(sum(wi*(abs(jerk)>=.95*jmax)*(jerk*res>0))/den) if den else None,'demand_slew_abs_gt150_fraction':float(sum(wi*(abs(dslew)>jmax))/den) if den else None,'demand_near25_fraction':float(sum(w*(abs(demand[:-1])>=.95*25))/sum(w)) if sum(w) else None}
 # Camera clocks stay source host-read, with separate observer receipts. Timing model diagnostic only.
 offset=float(np.quantile(np.array([s['received_ns']/1e9 for s in ss])-t,.01));ct0=low+offset;ct1=high+offset
 camera=[c for c in cam if c.get('t') is not None and ct0<=c['t']<=ct1];unique={}
 for c in camera:unique.setdefault(c['seq'],c)
 cc=sorted(unique.values(),key=lambda c:c['t']);valid=[c for c in cc if c.get('angle_valid',c.get('detected',False)) and c.get('theta_rad') is not None and not c.get('stale',False)]
 q={'envelopes':len(camera),'distinct_sequences':len(cc),'duplicate_envelopes':len(camera)-len(cc),'distinct_rate_hz':(len(cc)-1)/(cc[-1]['t']-cc[0]['t']) if len(cc)>1 else None,'valid_distinct':len(valid),'valid_fraction':len(valid)/len(cc) if cc else None,'stale_distinct_n':sum(c.get('stale',False) for c in cc),'camera_gap_ms_p50_p95_max':np.percentile(np.diff([c['t'] for c in cc])*1000,[50,95,100]).tolist(),'read_to_observer_ms_p50_p95_max':np.percentile([(c['receipt_s']-c['t'])*1000 for c in cc],[50,95,100]).tolist(),'source_read_to_result_ms_p50_p95_max':np.percentile([c['host_read_to_result_ms'] for c in cc],[50,95,100]).tolist() if all('host_read_to_result_ms' in c for c in cc) else None,'valid_confidence_p5_p50_p95':np.percentile([c['confidence'] for c in valid],[5,50,95]).tolist(),'camera_anchor_rad':ANCHOR,'source_host_read_window_s':[ct0,ct1],'source_clock_mapping':'native board plus per-run 1st percentile serial-receipt offset; camera t is host-read, not exposure'}
 # Match modes only for descriptive diagnostics using previously frozen effective19ms; do not apply shape map.
 tc=np.array([c['t'] for c in valid])-.019-offset;ii=np.searchsorted(t,tc);clip=np.clip(ii,1,len(t)-1);ok=(ii>0)&(ii<len(t))&((t[clip]-t[clip-1])<=.030);vcam=wrap(np.array([c['theta_rad'] for c in valid])-ANCHOR);enc=wrap(np.interp(tc,t,np.unwrap(th)));mcam=m[clip-1]
 q['receipt_age_over100ms_n']=sum(c['receipt_s']-c['t']>.100 for c in cc);q['valid_receipt_age_over100ms_n']=sum(c['receipt_s']-c['t']>.100 for c in valid);q['valid_source_gap_ms_p95_max']=np.percentile(np.diff([c['t'] for c in valid])*1000,[95,100]).tolist() if len(valid)>1 else None;q['calibration_identities']=list({json.dumps(c['calibration'],sort_keys=True) for c in cc if 'calibration' in c});q['alignment_effective_delay_ms']=19;q['angle_map_applied']=False;q['balance_aligned']={'n':int(sum(ok&(mcam==3)))}
 z=ok&(mcam==3)
 if sum(z):q['balance_aligned'].update({'camera_working_theta_rms_deg':float(np.sqrt(np.mean(vcam[z]**2))*R),'camera_working_abs_theta_p95_deg':float(np.quantile(abs(vcam[z]),.95)*R),'camera_minus_encoder_median_deg':float(np.median(wrap(vcam[z]-enc[z]))*R),'camera_minus_encoder_p5_p95_deg':np.percentile(wrap(vcam[z]-enc[z])*R,[5,95]).tolist()})
 result['camera']=q
 result['final']={'mode':report['final']['mode'],'flags':report['final']['flags'],'x':report['final']['x'],'fault':report['final']['fault'],'reference_raw':report['final_info']['encoder_upright_raw'],'i2c_errors':report['final_info']['i2c_errors']}
 return result

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=Path('/tmp/cartpole-retune-20261015'));ap.add_argument('--out',type=Path,default=Path('/tmp/cartpole-retune-20261015/bandwidth-analysis/results.json'));args=ap.parse_args();new=[analyze(d) for d in sorted((args.root/'natural351-bandwidth-trials').iterdir()) if d.is_dir()];old=[analyze(d) for d in sorted((args.root/'natural351-first-trials').glob('natural351-auto45*-*'))]
 out={'schema':'native-board-time-bandwidth-comparison-v1','analysis_window':'first 8 actual board-clock seconds after recorded motion-start STATE. No sample-count duration estimates.','episode_bounds':'entry between previous non-mode3 and first mode3 sample; exit between last mode3 and next non-mode3. Contiguous episodes split at >30 ms telemetry gaps.','actuation_caveat':'Acceleration/velocity are firmware commanded trajectory values, not measured motor acceleration. Finite differences expose interval-average jerk; near-cap fractions are duration weighted over same-mode intervals, without rail-brake latches.','trials':new,'prior_bw30_pw45':old};args.out.write_text(json.dumps(out,indent=2)+'\n')
 for r in new+old:
  print(r['name'], 'capture',r['first_capture_board_s'],'balance',r['balance']['total_lower_duration_s'],r['balance']['total_upper_duration_s'],'longest',r['balance']['longest_lower_s'],'episodes',[(round(e['first_s'],3),round(e['lower_duration_s'],3),e['end_mode_next']) for e in r['balance']['episodes']],'rail',r['rail_brake']['count'],r['mode_duration_left_hold_s'].get('5'),'jerkbal',r['actuation']['balance']['observed_avg_jerk_near150_fraction'],'residrms',r['actuation']['balance']['demand_minus_acceleration'].get('rms'),'cam',r['camera']['distinct_rate_hz'],r['camera']['valid_fraction'],r['camera']['balance_aligned'])
if __name__=='__main__':main()
