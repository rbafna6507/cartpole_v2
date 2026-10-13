"""Offline scientific analysis. Input CSVs are immutable; only derived files written."""
from pathlib import Path
import json, math
import numpy as np
from scipy.signal import find_peaks, savgol_filter
from scipy.optimize import least_squares
from scipy.integrate import solve_ivp
from scipy.special import ellipk

FIELDS='seq,t_us,dt_us,raw,ticks,theta,omega,status,agc,magnitude,i2c_errors,missed_slots,tx_drops,read_us,valid,continuous'.split(',') + 'cart_steps,x_command_m,v_command_m_s,a_command_m_s2,motion_id,moving,enabled,homed'.split(',')

def clean_json(x):
    if isinstance(x,dict):return {k:clean_json(v) for k,v in x.items()}
    if isinstance(x,(list,tuple,np.ndarray)):return [clean_json(v) for v in x]
    if isinstance(x,(np.integer,)):return int(x)
    if isinstance(x,(np.floating,float)):return float(x) if math.isfinite(x) else None
    if isinstance(x,np.bool_):return bool(x)
    return x

def write_json(path,obj):
    Path(path).write_text(json.dumps(clean_json(obj),indent=2,allow_nan=False)+'\n')

def circular_raw(raw):
    a=np.asarray(raw)*2*np.pi/4096
    return float(np.mod(np.angle(np.mean(np.exp(1j*a))),2*np.pi)*4096/(2*np.pi))

def delta_raw(raw,zero):return (np.asarray(raw)-zero+2048)%4096-2048

def angle_from_raw(raw,zero,calibration=None):
    delta=delta_raw(raw,zero)
    if calibration is None:return delta*2*np.pi/4096
    # Calibrated down reference is absolute sensor position; the per-trial zero
    # check must agree, otherwise moving magnet/assembly needs recalibration.
    drift=float(delta_raw(zero,calibration['zero_raw']))*2*np.pi/4096
    if abs(drift)>np.deg2rad(2):raise ValueError('Down zero changed >2 deg since static calibration; inspect/recalibrate.')
    delta=delta_raw(raw,calibration['zero_raw'])
    nodes=np.asarray(calibration['nodes_raw_delta_angle_rad'])
    if np.any(delta<nodes[0,0]) or np.any(delta>nodes[-1,0]):
        raise ValueError('Recording extends outside static calibration range; do not extrapolate. Calibrate wider angles or omit mapping.')
    return np.interp(delta,nodes[:,0],nodes[:,1])

def load_csv(path):
    d=np.genfromtxt(path,delimiter=',',names=True,ndmin=1)
    if len(d)<20:raise ValueError('Need at least 20 samples')
    names=d.dtype.names
    if 't_us' not in names or 'raw' not in names:raise ValueError('Expected t_us and raw columns')
    t=d['t_us'].astype(float)*1e-6
    # Legacy logs may wrap 32-bit micros; unwrap only large negative jumps.
    jumps=np.r_[0,np.cumsum(np.diff(t)<-2000)]
    t+=jumps*(2**32)*1e-6
    if not np.all(np.isfinite(t)):raise ValueError('Nonfinite timestamps')
    if np.any(np.diff(t)<=0):raise ValueError('Non-increasing timestamps; split at board resets, do not sort away the error')
    valid=(d['raw']>=0)&(d['raw']<4096)&np.isfinite(d['raw'])
    if 'valid' in names:valid&=d['valid']>0
    return d,t,valid

def quality(d,t,valid):
    names=d.dtype.names;dt=np.diff(t);good_dt=np.diff(t[valid]);st=d['status'][d['status']>=0] if 'status' in names else np.array([])
    return dict(samples=len(d),valid_samples=int(valid.sum()),invalid_samples=int((~valid).sum()),
        sample_rate_hz=1/np.median(dt),interval_jitter_us_std=np.std(dt)*1e6,max_gap_ms=np.max(dt)*1000,
        max_valid_gap_ms=np.max(good_dt)*1000 if len(good_dt) else None,
        sequence_gaps=int(np.maximum(0,np.diff(d['seq'])-1).sum()) if 'seq' in names else None,
        i2c_errors_total=int(np.max(d['i2c_errors'])) if 'i2c_errors' in names else None,
        missed_slots_total=int(np.max(d['missed_slots'])) if 'missed_slots' in names else None,
        tx_drops_total=int(np.max(d['tx_drops'])) if 'tx_drops' in names else None,
        unwrap_continuous=bool(np.all(d['continuous']>0)) if 'continuous' in names else None,
        magnet_status_samples=len(st),magnet_not_detected=int(np.sum((st.astype(int)&32)==0)),
        magnet_too_weak=int(np.sum((st.astype(int)&16)!=0)),magnet_too_strong=int(np.sum((st.astype(int)&8)!=0)),
        agc_min=float(np.min(d['agc'][d['agc']>=0])) if 'agc' in names and np.any(d['agc']>=0) else None,
        agc_max=float(np.max(d['agc'][d['agc']>=0])) if 'agc' in names and np.any(d['agc']>=0) else None,
        read_duration_median_us=float(np.median(d['read_us'])) if 'read_us' in names else None,
        read_duration_p99_us=float(np.percentile(d['read_us'],99)) if 'read_us' in names else None,
        timing_note='MCU read-midpoint timestamps; not AS5600 conversion timestamps. Host arrival is logged separately and is not sensor latency.')

def stationary(path):
    d,t,valid=load_csv(path)
    if valid.sum()<20:raise ValueError('Insufficient valid samples')
    raw=d['raw'][valid];zero=circular_raw(raw);a=delta_raw(raw,zero)*360/4096
    return dict(quality=quality(d,t,valid),zero_raw=zero,angle_std_deg=float(np.std(a)),
        angle_peak_to_peak_deg=float(np.ptp(a)),drift_deg_per_s=float(np.polyfit(t[valid]-t[valid][0],a,1)[0]),
        note='Noise statistics assume the pendulum was physically stationary; movement contributes to these values.')

def ode(t,p,y0,v0):
    w,b,c,offset=p
    def f(_,s):return [s[1],-w*w*np.sin(s[0])-b*s[1]-c*np.tanh(s[1]/.03)]
    sol=solve_ivp(f,(0,float(t[-1])),[y0-offset,v0],t_eval=t,rtol=1e-9,atol=1e-11,max_step=.025)
    if not sol.success or sol.y.shape[1]!=len(t):raise ValueError('ODE integration failed')
    return sol.y[0]+offset

def fit_dynamics(t,y):
    # Find first late positive/negative turning point below 35 deg; retain sign.
    dt=np.median(np.diff(t));s=savgol_filter(y,min(17,(len(y)//2)*2-1),3)
    allids=np.sort(np.r_[find_peaks(s,distance=max(1,int(.4/dt)),prominence=.01)[0],find_peaks(-s,distance=max(1,int(.4/dt)),prominence=.01)[0]])
    ids=allids[(np.abs(s[allids])<np.deg2rad(35))&(np.abs(s[allids])>np.deg2rad(8))]
    if len(ids)<1:raise ValueError('Need a clear peak between 8 and 35 degrees for dynamics fitting')
    first=ids[0];stopids=np.flatnonzero((t>t[first]+2)&(np.abs(s)>np.deg2rad(2)))
    last=stopids[-1] if len(stopids) else len(t)-1
    if t[last]-t[first]<2:raise ValueError('Need at least 2 s of useful decay')
    tf=np.arange(t[first],t[last],.01);yf=np.interp(tf,t,y);tf-=tf[0]
    peaks=find_peaks(yf,distance=40,prominence=.02)[0]
    rough=np.median(np.diff(tf[peaks])) if len(peaks)>=3 else .71
    initial=[2*np.pi/rough,.15,1.,0,yf[0],0]
    initial[0]=np.clip(initial[0],4.01,24.99)
    def residual(p):return ode(tf,p[:4],p[4],p[5])-yf
    fit=least_squares(residual,initial,bounds=([4,0,0,-.1,yf[0]-.12,-2],[25,3,8,.1,yf[0]+.12,2]),
        loss='soft_l1',f_scale=.015,diff_step=1e-4,max_nfev=120)
    prediction=ode(tf,fit.x[:4],fit.x[4],fit.x[5]);w,b,c,off,*_=fit.x
    return dict(w0_rad_s=w,beta_per_s=b,gamma_rad_s2=c,offset_rad=off,
        period_small_angle_s=2*np.pi/w,frequency_small_angle_hz=w/(2*np.pi),effective_length_m=9.80665/w**2,
        fit_rms_deg=np.rad2deg(np.sqrt(np.mean((prediction-yf)**2))),optimizer_success=fit.success,
        fit_start_relative_s=t[first],fit_end_relative_s=t[last],
        note='Provisional gravity + viscous + smooth dry-friction fit; no independent validation or parameter confidence intervals.'),tf+t[first],prediction

def analyze(path,release_s=None,zero_raw=None,calibration=None,fit=False):
    path=Path(path);d,t,valid=load_csv(path);q=quality(d,t,valid)
    tv=t[valid];raw=d['raw'][valid]
    if len(tv)<100:raise ValueError('Too few valid samples')
    relative=tv-t[0];warnings=[]
    if release_s is None:
        raise ValueError('Supply a release event or --release-s. Do not fit the hand-positioning segment.')
    if zero_raw is None:
        tail=raw[relative>relative[-1]-2]
        zero_raw=circular_raw(tail);warnings.append('Down zero inferred from final 2 s; confirm the arm was at rest there.')
    y=angle_from_raw(raw,zero_raw,calibration)
    chosen=relative>=release_s;relative=relative[chosen];y=y[chosen]
    if len(y)<100 or relative[-1]-relative[0]<2:raise ValueError('Too little post-release data')
    if np.max(np.diff(relative))>.020:raise ValueError('Post-release valid-data gap >20 ms: repeat recording or analyze a contiguous segment')
    if np.max(np.abs(np.diff(y)))>np.pi:raise ValueError('Angle crossed ±180 degrees: free-decay analysis requires libration, not full rotations')
    if q['magnet_not_detected'] or q['magnet_too_weak'] or q['magnet_too_strong']:warnings.append('AS5600 magnet status flags present; inspect raw status and placement.')
    if q['sequence_gaps']:warnings.append('Missing serial/scheduled samples; timing preserved, short gaps interpolated only for analysis.')
    tr=np.arange(relative[0],relative[-1],.002);yr=np.interp(tr,relative,y)
    # No moving-average phase lag in offline peak display; do not feed to controller.
    smooth=savgol_filter(yr,17,3);noise=np.std(yr-smooth);prom=max(.006,4*noise)
    pos=find_peaks(smooth,distance=200,prominence=prom)[0];neg=find_peaks(-smooth,distance=200,prominence=prom)[0]
    pos=pos[smooth[pos]>np.deg2rad(2)];neg=neg[smooth[neg]<-np.deg2rad(2)]
    period_rows=[];declines=[]
    for label,ids in [('positive',pos),('negative',neg)]:
        for a,b in zip(ids[:-1],ids[1:]):
            T=tr[b]-tr[a];A=(abs(smooth[a])+abs(smooth[b]))/2
            period_rows.append(dict(side=label,time_s=(tr[a]+tr[b])/2,amplitude_deg=np.rad2deg(A),period_s=T,
                finite_amplitude_corrected_period_s=T/(2/np.pi*ellipk(np.sin(A/2)**2))))
            if abs(smooth[b])>0:declines.append(np.log(abs(smooth[a])/abs(smooth[b])))
    ids=np.sort(np.r_[pos,neg]);amps=np.abs(smooth[ids]);sgn=np.sign(smooth[ids]);inc=[]
    for a,b in zip(range(len(ids)-1),range(1,len(ids))):
        if sgn[a]!=sgn[b] and amps[b]>amps[a]+np.deg2rad(2):inc.append(dict(time_s=tr[ids[b]],from_deg=np.rad2deg(amps[a]),to_deg=np.rad2deg(amps[b])))
    if inc:warnings.append('Some opposite-side turning amplitudes grow >2 deg: inspect zero, calibration, pivot motion or external forces.')
    small=[r['finite_amplitude_corrected_period_s'] for r in period_rows if 3<r['amplitude_deg']<25]
    metrics=dict(quality=q,zero_raw=zero_raw,release_s=release_s,calibration_applied=calibration is not None,
        peak_recorded_angle_deg=np.rad2deg(np.max(abs(y))),positive_peak_count=len(pos),negative_peak_count=len(neg),
        small_angle_period_estimate_s=np.median(small) if small else None,
        period_rows=period_rows,same_side_log_decrements=declines,opposite_side_growth_events=inc,
        warnings=warnings,notes=['Amplitude-corrected period assumes a simple gravity pendulum with weak damping.',
            'Signed decrements are preserved; growing peaks are not silently discarded.','No motor torque, cart mass, COM or actual cart displacement is inferred from arm angle alone.'])
    pred_t=pred=None
    if fit:
        try:metrics['dynamics_fit'],pred_t,pred=fit_dynamics(tr-tr[0],yr);pred_t+=tr[0]
        except ValueError as e:metrics['fit_error']=str(e)
    prefix=path.with_suffix('');write_json(str(prefix)+'_lab_metrics.json',metrics)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(3,1,figsize=(11,9))
    ax[0].plot(relative-release_s,np.rad2deg(y),lw=.6,label='Raw angle (zero/mapping applied)')
    ax[0].plot(tr-release_s,np.rad2deg(smooth),lw=1,label='Peak detection smooth')
    ax[0].scatter(tr[ids]-release_s,np.rad2deg(smooth[ids]),s=12)
    if pred is not None:ax[0].plot(pred_t-release_s,np.rad2deg(pred),'--',label='Provisional fitted dynamics')
    ax[0].set(ylabel='Angle from down (deg)',xlabel='Time since release (s)');ax[0].legend(fontsize=8)
    ax[1].plot(tr-release_s,np.gradient(smooth,tr));ax[1].set(ylabel='Offline angular velocity (rad/s)',xlabel='Time since release (s)')
    for label in ('positive','negative'):
        rows=[r for r in period_rows if r['side']==label]
        ax[2].plot([r['amplitude_deg'] for r in rows],[r['period_s'] for r in rows],'o-',label=label)
    ax[2].set(xlabel='Mean same-side amplitude (deg)',ylabel='Full period (s)');ax[2].legend();fig.tight_layout();fig.savefig(str(prefix)+'_lab_plot.png',dpi=150);plt.close(fig)
    return metrics

def export_model(metrics,mass_kg,com_m,output):
    f=metrics.get('dynamics_fit')
    if not f or not f['optimizer_success']:raise ValueError('Need a successful --fit run')
    if not (mass_kg>0 and com_m>0):raise ValueError('Positive measured mass and COM required')
    I=mass_kg*9.80665*com_m/f['w0_rad_s']**2
    if I<=mass_kg*com_m**2:raise ValueError('Nonphysical COM inertia; recheck measurements')
    write_json(output,dict(mass=mass_kg,com_dist=com_m,I_pivot=I,joint_damping=f['beta_per_s']*I,
        joint_frictionloss=f['gamma_rad_s2']*I,status='PROVISIONAL: validate on separate releases',fit=f,
        note='Input mass and COM must be measured. Compatible with prior make_mjcf(sysid=...).'))
