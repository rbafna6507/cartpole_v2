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

def analyze(d, firmware_manifest=None):
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
 result={'name':d.name,'parameters':dict(report['parameters']),'reference_raw':report['info']['encoder_upright_raw'],'reported_success':report['ok'],'source_hashes':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in [d/'report.json',d/'camera.json',log]},'time':{'board_window_start_s':low,'board_window_end_s':high,'source_state_n':len(allstates),'deduplicated_n':len(ss),'duplicate_tick_n':dup,'covered_interval_s':float(sum(weights)),'active_gap_ms_p50_p95_max':np.percentile(dt[weights>0]*1000,[50,95,100]).tolist(),'health_invalid_n':int(sum(~healthy[active]))},'mode_duration_left_hold_s':{str(k):float(sum(weights[m[:-1]==k])) for k in sorted(set(m[active]))}}
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
  result['actuation'][key]={'demand_minus_acceleration':stats(res,w),'theta_deg':stats(th[:-1]*R,w),'demand':stats(demand[:-1],w),'acceleration':stats(a[:-1],w),'residual_abs_gt_catch_da_fraction':float(sum(w*(abs(res)>report['parameters']['catch_da']))/sum(w)) if sum(w) else None,'jerk_cap_m_s3':jmax,'near_cap_fraction_threshold':.95,'jerk_interval_eligible_s':den,'observed_avg_abs_jerk_p50_p95_p99':quant(abs(jerk),wi),'observed_avg_jerk_near_cap_fraction':float(sum(wi*(abs(jerk)>=.95*jmax))/den) if den else None,'jerk_near_cap_and_toward_demand_fraction':float(sum(wi*(abs(jerk)>=.95*jmax)*(jerk*res>0))/den) if den else None,'demand_slew_abs_gt_jerk_cap_fraction':float(sum(wi*(abs(dslew)>jmax))/den) if den else None,'demand_near_acceleration_cap_fraction':float(sum(w*(abs(demand[:-1])>=.95*np.where(m[:-1]==2,report['parameters']['amax_s'],report['parameters']['amax_b'])))/sum(w)) if sum(w) else None}
 # Camera clocks stay source host-read, with separate observer receipts. Timing model diagnostic only.
 offset=float(np.quantile(np.array([s['received_ns']/1e9 for s in ss])-t,.01));ct0=low+offset;ct1=high+offset
 camera=[c for c in cam if c.get('t') is not None and ct0<=c['t']<=ct1];unique={}
 for c in camera:unique.setdefault(c['seq'],c)
 cc=sorted(unique.values(),key=lambda c:c['t']);valid=[c for c in cc if c.get('angle_valid',c.get('detected',False)) and c.get('theta_rad') is not None and not c.get('stale',False)]
 q={'envelopes':len(camera),'distinct_sequences':len(cc),'duplicate_envelopes':len(camera)-len(cc),'distinct_rate_hz':(len(cc)-1)/(cc[-1]['t']-cc[0]['t']) if len(cc)>1 else None,'valid_distinct':len(valid),'valid_fraction':len(valid)/len(cc) if cc else None,'stale_distinct_n':sum(c.get('stale',False) for c in cc),'camera_gap_ms_p50_p95_max':percentiles(np.diff([c['t'] for c in cc])*1000,[50,95,100]),'read_to_observer_ms_p50_p95_max':percentiles([(c['receipt_s']-c['t'])*1000 for c in cc],[50,95,100]),'source_read_to_result_ms_p50_p95_max':percentiles([c['host_read_to_result_ms'] for c in cc],[50,95,100]) if all('host_read_to_result_ms' in c for c in cc) else None,'valid_confidence_p5_p50_p95':percentiles([c['confidence'] for c in valid],[5,50,95]),'camera_anchor_rad':ANCHOR,'source_host_read_window_s':[ct0,ct1],'source_clock_mapping':'native board plus per-run 1st percentile serial-receipt offset; camera t is host-read, not exposure'}
 # Match modes only for descriptive diagnostics using previously frozen effective19ms; do not apply shape map.
 tc=np.array([c['t'] for c in valid])-.019-offset;ii=np.searchsorted(t,tc);clip=np.clip(ii,1,len(t)-1);ok=(ii>0)&(ii<len(t))&((t[clip]-t[clip-1])<=.030);vcam=wrap(np.array([c['theta_rad'] for c in valid])-ANCHOR);enc=wrap(np.interp(tc,t,np.unwrap(th)));mcam=m[clip-1]
 q['receipt_age_over100ms_n']=sum(c['receipt_s']-c['t']>.100 for c in cc);q['valid_receipt_age_over100ms_n']=sum(c['receipt_s']-c['t']>.100 for c in valid);q['valid_source_gap_ms_p95_max']=np.percentile(np.diff([c['t'] for c in valid])*1000,[95,100]).tolist() if len(valid)>1 else None;q['calibration_identities']=list({json.dumps(c['calibration'],sort_keys=True) for c in cc if 'calibration' in c});q['alignment_effective_delay_ms']=19;q['angle_map_applied']=False;q['balance_aligned']={'n':int(sum(ok&(mcam==3)))}
 z=ok&(mcam==3)
 if sum(z):q['balance_aligned'].update({'camera_working_theta_rms_deg':float(np.sqrt(np.mean(vcam[z]**2))*R),'camera_working_abs_theta_p95_deg':float(np.quantile(abs(vcam[z]),.95)*R),'camera_minus_encoder_median_deg':float(np.median(wrap(vcam[z]-enc[z]))*R),'camera_minus_encoder_p5_p95_deg':np.percentile(wrap(vcam[z]-enc[z])*R,[5,95]).tolist()})
 result['camera']=q
 result['final']={'mode':report['final']['mode'],'flags':report['final']['flags'],'x':report['final']['x'],'fault':report['final']['fault'],'reference_raw':report['final_info']['encoder_upright_raw'],'i2c_errors':report['final_info']['i2c_errors']}
 result['firmware_provenance']=firmware_provenance(d,report,firmware_manifest)
 result['source_report']={'records_dropped':report.get('records_dropped'),'error':report.get('error'),'reported_settling':report.get('settling')}
 result['settled_hanging']=settled_hanging(ss,cam,low,offset,report)
 start_pose=report.get('camera_start_pose');end_pose=report.get('camera_end_pose')
 delta=None
 if start_pose and end_pose and start_pose.get('pivot_px') and end_pose.get('pivot_px'):
  delta=(np.array(end_pose['pivot_px'])-start_pose['pivot_px']).tolist()
 result['home_return']={'reported_horizontal_delta_px':report.get('camera_return_delta_px'),'recomputed_delta_xy_px':delta,'start_pose':start_pose,'end_pose':end_pose,'final_counted_x_m':report['final']['x'],'metric_camera_cart_calibration_available':any(c.get('cart_valid',False) for c in cc)}
 return result

def percentiles(values, ps):
 return np.percentile(values,ps).tolist() if len(values) else [None]*len(ps)

def firmware_provenance(directory, report, supplied_manifest):
 info=report['info']; final=report.get('final_info',{})
 local=directory/'firmware-manifest.json'
 path=local if local.exists() else supplied_manifest
 out={'reported_version':info.get('firmware'),'final_reported_version':final.get('firmware'),'hex_sha256':None,'reference_initial_raw':info.get('encoder_upright_raw'),'reference_final_raw':final.get('encoder_upright_raw'),'source':'INFO reports version/reference; it does not attest a binary hash.'}
 if path is None:return out
 path=Path(path);content=path.read_bytes();manifest=json.loads(content)
 if manifest.get('firmware')!=info.get('firmware'):
  raise ValueError('firmware manifest version does not match trial INFO')
 matches=[(name,digest) for name,digest in manifest.get('hashes',{}).items() if name.endswith('.hex') and 'recovery' not in name.lower()]
 if len(matches)!=1:raise ValueError('firmware manifest must identify exactly one non-recovery hex')
 name,digest=matches[0]
 if len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):raise ValueError('invalid hex SHA256')
 out.update(hex_sha256=digest,hex_artifact=name,manifest_path=str(path),manifest_sha256=hashlib.sha256(content).hexdigest(),release=manifest.get('release'),source='Explicit release-manifest association, matched to INFO version; not a device hash readback.')
 return out

def settled_hanging(states, cameras, motion_board_s, offset, report):
 selected=[s for s in states if motion_board_s-1<=s['unwrapped_us']/1e6<=motion_board_s]
 out={'window':'last 1 actual board-clock second ending at recorded motion-start STATE','reported_settling':report.get('settling'),'state_n':len(selected),'board_duration_s':(selected[-1]['unwrapped_us']-selected[0]['unwrapped_us'])/1e6 if selected else None}
 if selected:
  theta=np.array([s['theta'] for s in selected]);scaled=theta*4096/(2*np.pi);raw=(np.rint(scaled).astype(int)+report['info']['encoder_upright_raw'])%4096
  out.update(raw_count_min_median_max=[int(min(raw)),float(np.median(raw)),int(max(raw))],count_decode_max_rounding_residual=float(max(abs(scaled-np.rint(scaled)))),theta_down_p5_median_p95_deg=percentiles(wrap(theta-np.pi)*R,[5,50,95]),theta_range_deg=float(np.ptp(np.unwrap(theta))*R),max_abs_native_omega=float(max(abs(s['omega']) for s in selected)),all_disabled_healthy=all((s['flags']&1) and not(s['flags']&2) and s['fault']==0 and s['mode']==0 for s in selected),max_abs_x_m=float(max(abs(s['x']) for s in selected)))
 cc={}
 for c in cameras:
  if c.get('t') is not None and motion_board_s-1+offset<=c['t']<=motion_board_s+offset:cc.setdefault(c['seq'],c)
 valid=[c for c in cc.values() if c.get('angle_valid',c.get('detected',False)) and c.get('theta_rad') is not None and not c.get('stale',False)]
 out['camera']={'distinct_n':len(cc),'valid_n':len(valid),'working_down_angle_p5_median_p95_deg':percentiles(wrap(np.array([c['theta_rad'] for c in valid])-ANCHOR-np.pi)*R,[5,50,95]),'read_to_observer_ms_p50_p95_max':percentiles([(c['receipt_s']-c['t'])*1000 for c in cc.values()],[50,95,100]),'clock_note':'Host-read source t, mapped using unchanged per-run lower-envelope receipt convention; no exposure claim.'}
 return out

def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('directories',nargs='+',type=Path,help='Trial directories containing report.json, camera.json, and rig-*.jsonl; order preserved.')
 ap.add_argument('--out',type=Path,required=True)
 ap.add_argument('--firmware-manifest',type=Path,help='Explicit release manifest for these trials; INFO firmware version must match. A per-trial firmware-manifest.json takes precedence.')
 args=ap.parse_args()
 rows=[analyze(d,args.firmware_manifest) for d in args.directories]
 result={'schema':'native-board-time-jerk-comparison-v1','analysis_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'analysis_window':'Requested duration in actual unwrapped board-clock seconds after recorded motion-start STATE, without sample-count duration estimates.','episode_bounds':'Entry lies between previous and first selected mode sample; exit between last and next. Gaps >30ms split contiguous episodes.','actuation_caveat':'Commanded trajectory acceleration, not physical motor acceleration. Interval-average jerk fractions are duration weighted and use the trial recorded jmax.','camera_caveat':'Current working anchor retained; 19ms previously frozen effective delay is descriptive only; no camera map applied.','trials':rows}
 args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
 for r in rows:
  print(json.dumps({'trial':r['name'],'jmax':r['parameters']['jmax'],'capture_s':r['first_capture_board_s'],'balance_lower_s':r['balance']['total_lower_duration_s'],'longest_balance_s':r['balance']['longest_lower_s'],'rail_brake_count':r['rail_brake']['count'],'balance_jerk_near_cap_fraction':r['actuation']['balance']['observed_avg_jerk_near_cap_fraction'],'camera_return_delta_px':r['home_return']['reported_horizontal_delta_px'],'firmware_sha256':r['firmware_provenance']['hex_sha256']}))
if __name__=='__main__':main()
