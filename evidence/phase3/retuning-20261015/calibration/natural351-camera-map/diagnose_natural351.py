exec(open('/tmp/analyze_natural351.py').read().split('\nresult={')[0])
m=json.loads(Path('/tmp/cartpole-retune-20261015/natural351-map-exploration.json').read_text()); lag=m['models']['f2']['lag_ms']/1000;b=np.array(m['models']['f2']['coef_rad'])
out={'working_upright_anchor':{},'first_two_auto':[]}
a=[v for v in ps if end-10<=v['state']['received_ns']/1e9<=end];c=[v['snapshot'] for v in pc if end-10<=v['snapshot'].get('t',0)<=end and v['snapshot'].get('angle_valid')];out['working_upright_anchor']={'window_start_host_s':end-10,'window_end_host_s':end,'state_n':len(a),'raw_count_min_median_max':[min(v['raw_count'] for v in a),float(np.median([v['raw_count'] for v in a])),max(v['raw_count'] for v in a)],'camera_n':len(c),'camera_theta_anchor_rad':anchor,'camera_relative_degrees_pcts_0_5_50_95_100':np.percentile(wrap(np.array([v['theta_rad'] for v in c])-anchor)*R,[0,5,50,95,100]).tolist(),'camera_span_px_pcts':np.percentile([v['length_px'] for v in c],[0,5,50,95,100]).tolist(),'camera_pivot_mean_px':np.mean([v['pivot_px'] for v in c],0).tolist()}
for r in runs:
 x=samples(r,lag);print('\n',r['name']);row={'run':r['name'],'subsets':{}}
 for name,sel in [('all',np.ones(len(x),bool)),('near_upright_15deg',abs(x[:,0]*R)<15),('near_upright_5deg',abs(x[:,0]*R)<5),('slow_abs_omega_lt1',abs(x[:,2])<1),('fast_abs_omega_gt5',abs(x[:,2])>5),('positive_rate_gt1',x[:,2]>1),('negative_rate_lt_minus1',x[:,2]<-1),('mode3_balance',x[:,4]==3),('first_half',x[:,3]<4),('last_half',x[:,3]>=4)]:
  z=x[sel];err=wrap(z[:,1]-basis(z,'f2')@b)*R
  if len(z):v={'n':len(z),'raw_cam_minus_encoder_median_deg':float(np.median(z[:,1]*R)),'raw_range_deg':np.percentile(z[:,1]*R,[0,5,95,100]).tolist(),'f2_metrics':metrics(z,'f2',b)};row['subsets'][name]=v;print(name,v)
 pre=[c for c in r['cam'] if r['start']-.8<=c['t']<=r['start']-.05 and c['detected']]
 prestate=[s for s in r['states'] if r['start']-.8<=s['received_ns']/1e9<=r['start']-.05]
 row['pre_run_hanging']={'camera_n':len(pre),'state_n':len(prestate),'encoder_theta_deg':float(np.median([s['theta'] for s in prestate]))*R,'camera_theta_relative_deg':float(np.median(wrap(np.array([c['theta_rad'] for c in pre])-anchor-np.pi))+np.pi)*R,'raw_median':float(np.median([(round(s['theta']*4096/(2*np.pi))+351)%4096 for s in prestate]))}
 print('PRE',row['pre_run_hanging']);out['first_two_auto'].append(row)
print('ANCHOR',out['working_upright_anchor']);print('BINS',m['a2_angle_direction_bins']);print('LAG SENS',m['a2_lag_sensitivity'])
# Compare dynamic signed-rate residual after the free-offset model at matched angle bins.
x=np.vstack([samples(r,lag) for r in runs]);out['free_offset_shape_direction_bins']=[]
for lo in range(-180,180,30):
 row={'lo_deg':lo};sel=(x[:,0]*R>=lo)&(x[:,0]*R<lo+30)
 for name,mask in [('positive',x[:,2]>1),('negative',x[:,2]<-1),('slow',abs(x[:,2])<=1)]:
  z=x[sel&mask];row[name]={'n':len(z),'median_residual_deg':float(np.median(wrap(z[:,1]-basis(z,'f2')@b)*R)) if len(z) else None}
 out['free_offset_shape_direction_bins'].append(row)
out['free_offset_shape_lag_sensitivity']=[{'lag_ms':ll*1000,'metrics':metrics(np.vstack([samples(r,ll) for r in runs]),'f2',b)} for ll in [lag-.010,lag-.005,lag,lag+.005,lag+.010]]
Path('/tmp/cartpole-retune-20261015/natural351-map-diagnostics.json').write_text(json.dumps(out,indent=2)+'\n')
