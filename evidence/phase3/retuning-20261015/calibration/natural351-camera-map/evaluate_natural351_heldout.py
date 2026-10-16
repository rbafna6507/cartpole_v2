exec(open('/tmp/analyze_natural351.py').read().split('\nresult={')[0])
frozen=Path('/tmp/cartpole-retune-20261015/natural351-frozen-training.json');models=json.loads(frozen.read_text());anchor=models['anchor_theta_rad']
held=[]
for d in sorted(P.glob('natural351-auto*b-*')):
 rep=json.loads((d/'report.json').read_text());cam=json.loads((d/'camera.json').read_text());events=[json.loads(l) for l in next(d.glob('rig-*.jsonl')).read_text().splitlines()];states=[e['state'] for e in events if e['type']=='state'];board=np.array([s['unwrapped_us']/1e6 for s in states]);recv=np.array([s['received_ns']/1e9 for s in states]);origin=float(np.quantile(recv-board,.01));time=board+origin;theta=np.unwrap([s['theta'] for s in states]);omega=np.array([s['omega'] for s in states]);mode=np.array([s['mode'] for s in states]);start=rep['motion_start']['received_ns']/1e9;valid=[]
 for c in cam:
  if not(start<=c['t']<=start+8) or not c['detected'] or c['pivot_px'] is None or c['bob_px'] is None: continue
  dx,dy=np.array(c['bob_px'])-c['pivot_px'];raw=math.atan2(dx,dy);target=float(wrap(np.pi-raw-0.006486665936711519-anchor));valid.append(dict(c,target=target,length=math.hypot(dx,dy)))
 held.append(dict(name=d.name.split('-')[1],path=str(d),report=rep,time=time,theta=theta,omega=omega,mode=mode,valid=valid,cam=cam,states=states,start=start,origin=origin,latency=(recv-board-origin)*1000))
out={'frozen_training_sha256':hashlib.sha256(frozen.read_bytes()).hexdigest(),'no_refit':True,'models':{},'quality':[],'heldout_source_sha256':{}}
for r in held:
 active=[c for c in r['cam'] if r['start']<=c['t']<=r['start']+8];x=samples(r,.019)
 q={'run':r['name'],'active_camera_n':len(active),'detected_n':sum(c['detected'] for c in active),'admitted_at_19ms':len(x),'encoder_health_invalid_total':sum(s['fault']!=0 or (s['flags']&1)==0 for s in r['states']),'angle_bin_counts':np.histogram(x[:,0]*R,bins=np.arange(-180,181,30))[0].tolist(),'camera_gap_ms_pcts':np.percentile(np.diff([c['t'] for c in active])*1000,[0,50,95,100]).tolist(),'read_to_observer_ms_pcts':np.percentile([(c['receipt_s']-c['t'])*1000 for c in active],[0,50,95,100]).tolist(),'reference':r['report']['info']['encoder_upright_raw']}
 pre=[c for c in r['cam'] if r['start']-.8<=c['t']<=r['start']-.05 and c['detected']];ss=[s for s in r['states'] if r['start']-.8<=s['received_ns']/1e9<=r['start']-.05];q['pre_run_hanging']={'camera_n':len(pre),'state_n':len(ss),'encoder_theta_deg':float(np.median([s['theta'] for s in ss]))*R,'camera_theta_relative_deg':float(np.median(wrap(np.array([c['theta_rad'] for c in pre])-anchor-np.pi))+np.pi)*R,'raw_median':float(np.median([(round(s['theta']*4096/(2*np.pi))+351)%4096 for s in ss]))}
 out['quality'].append(q)
 for f in Path(r['path']).iterdir():
  if f.suffix in ['.json','.jsonl']:out['heldout_source_sha256'][str(f.relative_to(P))]=hashlib.sha256(f.read_bytes()).hexdigest()
print('QUALITY',json.dumps(out['quality']))
for kind in ['raw','offset','a2','f2','a2h']:
 model=models['models'][kind];lag=model['lag_ms']/1000;b=np.array(model['coef_rad']);xx=[samples(r,lag) for r in held];v={'lag_ms':lag*1000,'coef_rad':b.tolist(),'pooled':metrics(np.vstack(xx),kind,b),'runs':{r['name']:metrics(x,kind,b) for r,x in zip(held,xx)}}
 if kind=='f2':
  v['subsets']={}
  for r,x in zip(held,xx):
   zz={}
   for name,sel in [('near_upright_5deg',abs(x[:,0]*R)<5),('near_upright_15deg',abs(x[:,0]*R)<15),('mode3',x[:,4]==3),('positive_rate_gt1',x[:,2]>1),('negative_rate_lt_minus1',x[:,2]<-1)]:
    z=x[sel]
    if len(z):zz[name]={'metrics':metrics(z,kind,b),'camera_minus_encoder_median_deg':float(np.median(z[:,1]*R))}
   v['subsets'][r['name']]=zz
  allr=runs+held;v['quality_sensitivity_without_refit']={}
  for r in allr:
   z=samples(r,lag);strict=(z[:,5]>=125)&(z[:,5]<=145)&(z[:,6]>=.85);v['quality_sensitivity_without_refit'][r['name']]=metrics(z[strict],kind,b)
 out['models'][kind]=v;print(kind,json.dumps(v))
Path('/tmp/cartpole-retune-20261015/natural351-heldout-evaluation.json').write_text(json.dumps(out,indent=2)+'\n')
