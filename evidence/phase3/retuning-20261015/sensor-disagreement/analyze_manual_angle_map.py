"""Offline slow-manual-turn camera/encoder comparison; never writes calibration."""
from pathlib import Path
import json,gzip,hashlib
import numpy as np
from scipy.signal import savgol_filter
from scipy.optimize import least_squares
P=Path('/tmp/cartpole-retune-20261015');path=P/'manual-angle-map-compact.json.gz';r=json.loads(gzip.decompress(path.read_bytes()));s=r['states'];wrap=lambda x:np.arctan2(np.sin(x),np.cos(x));rms=lambda x:float(np.sqrt(np.mean(np.asarray(x)**2)));basis=lambda q:np.column_stack([np.ones_like(q),np.sin(q),np.cos(q),np.sin(2*q),np.cos(2*q)])
board=np.array([a['unwrapped_us'] for a in s])/1e6;host=np.array([a['received_ns'] for a in s])/1e9;bt=board-board[0];scale=np.polyfit(bt,host-host[0],1)[0];base=np.median(host-scale*bt);st=base+scale*bt;uq=np.unwrap([a['theta'] for a in s]);c=[c for c in r['camera'] if c.get('detected') and c.get('pivot_px') and c.get('bob_px') and c.get('confidence',0)>.7 and np.linalg.norm(np.subtract(c['bob_px'],c['pivot_px']))>80];ct=np.array([a['t'] for a in c]);piv=np.array([a['pivot_px'] for a in c]);bob=np.array([a['bob_px'] for a in c]);cam=np.arctan2(bob[:,0]-piv[:,0],piv[:,1]-bob[:,1]);t=ct-st[0];lag=-.023;q=wrap(np.interp(ct+lag,st,uq));uqi=np.interp(ct+lag,st,uq);diff=wrap(cam-q);rate=np.interp(ct+lag,st,np.gradient(savgol_filter(uq,21,2),st));moving=(t>=40)&(t<=74)&(abs(rate)>.03);out={'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'reference_changed':r['reference_changed'],'reference_start':r['info']['encoder_upright_raw'],'reference_end':r['final_info']['encoder_upright_raw'],'all_modes':sorted(set(a['mode'] for a in s)),'all_x':sorted(set(a['x'] for a in s)),'disabled_all':all(not(a['flags']&2) for a in s),'lag_s':lag,'coverage':{'encoder_unwrapped_range_rad':[float(min(uq)),float(max(uq))],'net_encoder_turn_rad':float(uq[-1]-uq[0]),'moving_camera_samples':int(sum(moving)),'motion_interval_s':[40,74],'limitation':'One complete negative traversal only; no complete positive traversal. Directional calibration/hysteresis not validated.'},'stationary_windows':{},'angle_bins':[]}
for label,mask in [('before',t<35),('after',t>85),('near_upright',moving&(abs(q)<.15))]:
 cm=np.arctan2(np.mean(np.sin(cam[mask])),np.mean(np.cos(cam[mask])));em=np.arctan2(np.mean(np.sin(q[mask])),np.mean(np.cos(q[mask])));out['stationary_windows'][label]={'n':int(sum(mask)),'camera_mean_rad':float(cm),'camera_std_rad':float(np.std(wrap(cam[mask]-cm))),'encoder_mean_rad':float(em),'encoder_std_rad':float(np.std(wrap(q[mask]-em))),'camera_minus_encoder_mean_rad':float(np.mean(diff[mask])),'camera_minus_encoder_std_rad':float(np.std(diff[mask]))}
for mid in np.arange(-np.pi+np.pi/12,np.pi,np.pi/6):
 mask=moving&(abs(wrap(q-mid))<np.pi/12);z={'center_encoder_rad':float(mid),'n':int(sum(mask))}
 if sum(mask):z.update(disagreement_mean_rad=float(np.mean(diff[mask])),disagreement_median_rad=float(np.median(diff[mask])),disagreement_std_rad=float(np.std(diff[mask])))
 out['angle_bins'].append(z)
# Descriptive map only: one direction cannot establish calibration repeatability.
fit=np.linalg.lstsq(basis(q[moving]),diff[moving],rcond=None)[0];const=np.mean(diff[moving]);pred=basis(q)@fit;out['descriptive_fit']={'features':['1','sin(q)','cos(q)','sin(2q)','cos(2q)'],'coefficients_rad':fit.tolist(),'constant_rms_rad':rms(diff[moving]-const),'harmonic_rms_rad':rms(diff[moving]-pred[moving]),'warning':'Fit on all moving samples is descriptive only; no direction-heldout test exists.'}
# Lag sensitivity bounds are a transparent sensitivity check, not an estimate.
lag_results=[]
for dl in [-.05,0,.05]:
 qq=wrap(np.interp(ct+lag+dl,st,uq));dd=wrap(cam-qq);ff=np.linalg.lstsq(basis(qq[moving]),dd[moving],rcond=None)[0];lag_results.append({'lag_s':lag+dl,'coefficients_rad':ff.tolist(),'rms_rad':rms(dd[moving]-basis(qq[moving])@ff),'near_up_mean_disagreement_rad':float(np.mean(dd[moving&(abs(qq)<.15)]))})
out['lag_sensitivity']=lag_results
b=out['stationary_windows']['before'];a=out['stationary_windows']['after'];out['same_down_pose_change']={'encoder_rad':float(wrap(a['encoder_mean_rad']-b['encoder_mean_rad'])),'camera_rad':float(wrap(a['camera_mean_rad']-b['camera_mean_rad'])),'encoder_minus_camera_rad':float(wrap((a['encoder_mean_rad']-b['encoder_mean_rad'])-(a['camera_mean_rad']-b['camera_mean_rad'])))}
# Retain synchronized samples to reproduce figures and distinguish local direction.
out['pairs']=[{'t_s':float(tt),'encoder_rad':float(ee),'camera_rad':float(cc),'camera_minus_encoder_rad':float(dd),'smoothed_encoder_rate_rad_s':float(ww),'moving':bool(mm)} for tt,ee,cc,dd,ww,mm in zip(t,q,cam,diff,rate,moving)]
# Camera-only circle/ellipse consistency: includes slow pauses, independent of encoder map.
vec=(bob-piv)[(t>40)&(t<74)];rr=np.linalg.norm(vec,axis=1);vec=vec[(rr>120)&(rr<220)]
def ellipse_residual(par):
 cx,cy,rx,ry,phi=par;dd=vec-[cx,cy];xx=np.cos(phi)*dd[:,0]+np.sin(phi)*dd[:,1];yy=-np.sin(phi)*dd[:,0]+np.cos(phi)*dd[:,1];return np.sqrt((xx/rx)**2+(yy/ry)**2)-1
ell=least_squares(ellipse_residual,[0,0,163,163,0],bounds=([-50,-50,100,100,-4],[50,50,220,220,4]),loss='soft_l1',f_scale=.015);cx,cy,rx,ry,phi=ell.x
out['camera_ellipse_geometry']={'n':len(vec),'center_relative_marker_px':[float(cx),float(cy)],'radii_px':[float(rx),float(ry)],'axis_ratio':float(max(rx,ry)/min(rx,ry)),'rotation_rad':float(phi),'normalized_residual_rms':rms(ellipse_residual(ell.x)),'caveat':'Weak perspective, rigid circle, and correct marker detection assumptions; descriptive fit, no calibrated uncertainty bound.'}
(P/'manual-angle-map-analysis.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k!='pairs'},indent=2))
