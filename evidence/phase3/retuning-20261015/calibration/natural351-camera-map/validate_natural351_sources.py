exec(open('/tmp/evaluate_natural351_heldout.py').read().split('\nout={')[0])
out={}
for r in runs+held:
 s=r['states'];c=r['cam'];dups=[(a,b) for a,b in zip(s,s[1:]) if a['unwrapped_us']==b['unwrapped_us']];unique=np.r_[True,np.diff(r['time'])>0]
 v={'state_n':len(s),'health_invalid_n':sum(not((x['flags']&1) and x['fault']==0) for x in s),'board_rollback_n':int(np.sum(np.diff(r['time'])<0)),'duplicate_tick_n':len(dups),'duplicates_identical_theta':all(a['theta']==b['theta'] for a,b in dups),'duplicate_receipt_relative_to_motion_start_s':[b['received_ns']/1e9-r['start'] for a,b in dups],'receipt_monotonic':all(b['received_ns']>a['received_ns'] for a,b in zip(s,s[1:])),'camera_unique_sequence':len({x['seq'] for x in c})==len(c),'camera_time_increasing':all(b['t']>a['t'] for a,b in zip(c,c[1:])),'max_interpolated_change_after_dedup_rad':0.0}
 for k in ['raw','offset','a2','f2','a2h']:
  lag=models['models'][k]['lag_ms']/1000;t=np.array([x['t'] for x in r['valid']])-lag
  before=np.interp(t,r['time'],r['theta']);after=np.interp(t,r['time'][unique],r['theta'][unique]);v['max_interpolated_change_after_dedup_rad']=max(v['max_interpolated_change_after_dedup_rad'],float(max(abs(after-before))))
 assert v['health_invalid_n']==0 and v['board_rollback_n']==0 and v['duplicates_identical_theta'] and v['receipt_monotonic'] and v['camera_unique_sequence'] and v['camera_time_increasing'] and v['max_interpolated_change_after_dedup_rad']==0
 out[r['name']]=v
Path('/tmp/cartpole-retune-20261015/natural351-source-validation.json').write_text(json.dumps({'scope':'Validation only, no coefficient, lag, or clock-map refit. Duplicate board samples do not create extra camera comparison samples.','runs':out},indent=2)+'\n')
print('All four runs: healthy sources, no clock rollback, unique/increasing camera samples. Repeated board ticks have identical theta; removing them with the frozen time map changes every compared angle by exactly zero.')
