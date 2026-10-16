"""Raw camera horizontal crossings and weak-perspective marker-offset check."""
from pathlib import Path
import gzip,json,hashlib
import numpy as np
from scipy.optimize import least_squares,brentq
P=Path('/tmp/cartpole-retune-20261015');wrap=lambda x:np.arctan2(np.sin(x),np.cos(x));rms=lambda x:float(np.sqrt(np.mean(np.asarray(x)**2)))
reports=json.loads(gzip.decompress((P/'upright370-partial.json.gz').read_bytes()));cams=json.loads(gzip.decompress((P/'upright370-cameras.json.gz').read_bytes()));cm={x['path'].removesuffix('/camera.json'):x['camera'] for x in cams};prior=json.loads((P/'upright370-camera-comparison.json').read_text());pr={x['run']:x for x in prior['runs']};out={'method':{'crossing':'zero of bob-minus-pivot dy - track_slope*dx; raw marker positions; interpolation bracket<120ms','timing':'lag estimated from earlier swing comparison, frozen; telemetry board clock linearly mapped to host','zero_convention':'target +/-pi/2 minus encoder at crossing; positive means encoder reads below rail-relative orientation','ellipse':'fit bob-minus-pivot point cloud to a free centered ellipse under weak-perspective assumption; no encoder angle used','limits':['Rail-normal is gravity-upright only if rail is physically level.','Horizontal-crossing method requires red marker at actual hinge and blue marker on pole axis.','Perspective/nonplanar motion and marker offsets can break the simple ellipse-center interpretation.','Camera15Hz and encoder high-rate chatter limit crossing timing; report linear-vs-cubic sensitivity and direction spread, not a calibrated confidence interval.']},'runs':[]}
for z in reports:
 r=z['report'];rid=z['result']['run'];pp=pr[rid];s=r['states'];board=np.array([a['unwrapped_us'] for a in s])/1e6;host=np.array([a['received_ns'] for a in s])/1e9;bt=board-board[0];slope=np.polyfit(bt,host-host[0],1)[0];base=np.median(host-slope*bt);st=base+slope*bt;uq=np.unwrap([a['theta'] for a in s]);mode=np.array([a['mode'] for a in s]);c=[c for c in cm[r['path']] if c.get('detected') and c.get('confidence',0)>=.7 and c.get('pivot_px') and c.get('bob_px') and (c.get('age_since_host_read_s') or 0)<.2];ct=np.array([c['t'] for c in c]);pivot=np.array([c['pivot_px'] for c in c]);bob=np.array([c['bob_px'] for c in c]);v=bob-pivot;auto=(ct>=st[0])&(ct<st[0]+12)
 # Robust image track fit rejects occasional marker-detector jumps.
 ox=np.median(pivot[auto,0]);ff=least_squares(lambda k:pivot[auto,1]-(k[0]*(pivot[auto,0]-ox)+k[1]),[.015,np.median(pivot[auto,1])],loss='soft_l1',f_scale=.8);track_slope=float(ff.x[0]);normal=float(np.arctan(track_slope));dy=v[:,1]-track_slope*v[:,0]
 row={'run':rid,'candidate':z['result']['candidate'],'track_slope_dy_dx':track_slope,'track_normal_angle_rad':normal,'crossings':[]};lag=pp['lag_s']
 for j in np.flatnonzero(dy[:-1]*dy[1:]<0):
  if not(auto[j] and auto[j+1]) or ct[j+1]-ct[j]>.12:continue
  tc=ct[j]-dy[j]*(ct[j+1]-ct[j])/(dy[j+1]-dy[j]);dx=np.interp(tc,ct,v[:,0]);target=np.sign(dx)*np.pi/2;en=float(wrap(np.interp(tc+lag,st,uq)));idx=np.clip(np.searchsorted(st,tc+lag)-1,0,len(st)-1);qq={'elapsed_s':float(tc-st[0]),'side':'right' if dx>0 else 'left','direction':'dy_increasing' if dy[j+1]>dy[j] else 'dy_decreasing','encoder_rad':en,'rail_relative_minus_encoder_rad':float(wrap(target-en)),'camera_bracket_s':float(ct[j+1]-ct[j]),'mode':int(mode[idx])}
  if j>=1 and j+2<len(ct) and max(np.diff(ct[j-1:j+3]))<.13:
   poly=np.polyfit(ct[j-1:j+3]-tc,dy[j-1:j+3],3)
   try:
    dt=brentq(lambda t:np.polyval(poly,t),ct[j]-tc,ct[j+1]-tc);encubic=float(wrap(np.interp(tc+dt+lag,st,uq)));qq.update(cubic_interpolation_time_change_s=float(dt),cubic_rail_relative_minus_encoder_rad=float(wrap(target-encubic)))
   except ValueError:pass
  row['crossings'].append(qq)
 vv=v[auto];rr=np.linalg.norm(vv,axis=1);vv=vv[(rr>80)&(rr<250)]
 def ellipse(par,points):
  cx,cy,rx,ry,angle=par;co,si=np.cos(angle),np.sin(angle);d=points-[cx,cy];x=co*d[:,0]+si*d[:,1];y=-si*d[:,0]+co*d[:,1];return np.sqrt((x/rx)**2+(y/ry)**2)-1
 fits=[]
 for angle in [0,.5,1.]:
  f=least_squares(ellipse,[0,0,170,170,angle],args=(vv,),bounds=([-100,-100,80,80,-3.2],[100,100,300,300,3.2]),loss='soft_l1',f_scale=.02,max_nfev=1500);fits.append(f)
 f=min(fits,key=lambda f:sum(ellipse(f.x,vv)**2));cx,cy,rx,ry,phi=f.x
 row['weak_perspective_ellipse']={'points':len(vv),'center_relative_to_red_marker_px':[float(cx),float(cy)],'radii_px':[float(rx),float(ry)],'rotation_rad':float(phi),'normalized_radial_residual_rms':rms(ellipse(f.x,vv)),'max_marker_center_angle_bias_bound_rad':float(np.arcsin(min(1,np.hypot(cx,cy)/min(rx,ry))))}
 vals=[x['rail_relative_minus_encoder_rad'] for x in row['crossings']];row['crossing_summary']={'n':len(vals),'mean_rad':float(np.mean(vals)),'median_rad':float(np.median(vals)),'p05_p95_rad':np.quantile(vals,[.05,.95]).tolist(),'by_side':{}}
 for side in ['right','left']:
  vals=[x['rail_relative_minus_encoder_rad'] for x in row['crossings'] if x['side']==side];row['crossing_summary']['by_side'][side]={'n':len(vals),'median_rad':float(np.median(vals)),'mean_rad':float(np.mean(vals))}
 out['runs'].append(row);print(rid,row['candidate'],'roll',round(normal,4),'cross',row['crossing_summary'],'ellipse',row['weak_perspective_ellipse'])
(P/'upright370-horizontal-geometry.json').write_text(json.dumps(out,indent=2)+'\n')
