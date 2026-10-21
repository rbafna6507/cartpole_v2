#!/usr/bin/env python3
"""Local, read-only input audit; no hardware transport, training, or model fitting.

Run from repository root: PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1
OPENBLAS_NUM_THREADS=1 .venv/bin/python evidence/policy-recovery-20261021/
transfer-audit/audit.py --output /tmp/transfer-audit-reproduction
Output must not already exist. Historical traces and actors remain immutable.
"""
import argparse
from dataclasses import asdict
import gzip
from hashlib import sha256
import json
import math
from pathlib import Path
import numpy as np
from cartpole_sdk.control.parameters import ControllerParameters, gains
from cartpole_sdk.control.reference import estimate, balance
from cartpole_sdk.control.motion import settled_velocity_accel
from cartpole_sdk.policies.numeric_backend import NumpyActorBackend
from cartpole_sdk.policies.neural import validate_actor

ROOT=Path(__file__).resolve().parents[3]
INPUTS={}

def read(path):
    p=ROOT/path; raw=p.read_bytes(); INPUTS[str(path)]=dict(sha256=sha256(raw).hexdigest(),bytes=len(raw))
    return gzip.decompress(raw) if p.suffix=='.gz' else raw

def js(path): return json.loads(read(path))
def stats(x):
    a=np.asarray(x,dtype=float)
    if not len(a):return None
    assert np.isfinite(a).all()
    return dict(n=len(a),min=float(a.min()),max=float(a.max()),mean=float(a.mean()),rms=float(np.sqrt(np.mean(a*a))),p50=float(np.median(a)),p95=float(np.percentile(a,95)),p99=float(np.percentile(a,99)))

def enc(s,filtered=False):
    theta=s['angle_hat'] if filtered else s['theta']
    return dict(age_s=[0.]*7,state=[s['x'],s['velocity'],math.sin(theta),math.cos(theta),s['omega'],s['acceleration'],s['brake_direction']],valid=[1]*7)

def pred(net, q):
    x,v,theta,omega,a=q
    return net.predict_encoded(dict(age_s=[0.]*7,state=[x,v,math.sin(theta),math.cos(theta),omega,a,0.],valid=[1]*7))

def load_actor(name):
    a=js(Path('training/candidates')/name/'actor.json');validate_actor(a)
    net=NumpyActorBackend(a);z=np.zeros(5)
    derivative=[]
    for i in range(5):
        d=np.zeros(5);d[i]=1e-5
        derivative.append((pred(net,z+d)-pred(net,z-d))/2e-5)
    # Independent finite difference convergence, no fitted coefficients.
    for i in range(5):
        d=np.zeros(5);d[i]=2e-5
        assert abs((pred(net,z+d)-pred(net,z-d))/4e-5-derivative[i])<1e-5
    p=ControllerParameters(**a['executor_parameters'])
    return net,dict(content_sha256=a['content_sha256'],checkpoint_sha256=a['checkpoint_sha256'],angle_source=a['angle_source'],rate_hz=a['rate_hz'],bias_m_s2=pred(net,z),jacobian_order=['x','v','theta','omega','governed_acceleration'],jacobian=derivative,auto_gains=asdict(gains(p)),bal_gains=asdict(gains(p,upright=True)))

def spectral(t,x,low=2.,high=15.):
    # Descriptive only: finite-window FFT of linearly detrended, Hann-windowed data.
    if len(t)<30:return None
    dt=float(np.median(np.diff(t))); grid=np.arange(t[0],t[-1]+dt*.2,dt)
    y=np.interp(grid,t,x);y-=np.polyval(np.polyfit(grid-grid[0],y,1),grid-grid[0])
    amp=np.abs(np.fft.rfft(y*np.hanning(len(y))))
    freq=np.fft.rfftfreq(len(y),dt);use=(freq>=low)&(freq<=high)
    pick=np.flatnonzero(use)[np.argmax(amp[use])]
    return dict(peak_hz=float(freq[pick]),bin_width_hz=float(1/(len(y)*dt)),window_s=[float(t[0]),float(t[-1])],samples=len(y),semantics='Descriptive finite-window peak; growing transient, not an identified eigenfrequency.')

def phase_sine(y,t,f):
    mat=np.column_stack([np.sin(2*np.pi*f*t),np.cos(2*np.pi*f*t),np.ones(len(t))])
    coeff=np.linalg.lstsq(mat,y,rcond=None)[0]
    return complex(coeff[0],coeff[1])

def observer_response():
    f=6.;dt=.001;A=.001;h=r=0.;vals=[]
    # Exercise exact current simulation observer, preserving its binary32 angle wrapping.
    for n in range(12000):
        t=n*dt;raw=A*math.sin(2*math.pi*f*t);h,r=estimate(raw,h,r,10.)
        if n>=2000:vals.append((t,raw,h,r))
    m=np.asarray(vals);raw=phase_sine(m[:,1],m[:,0],f)
    out={}
    for key,col,den in [('angle_over_raw',2,raw),('rate_over_true_rate',3,1j*2*math.pi*f*raw)]:
        z=phase_sine(m[:,col],m[:,0],f)/den
        out[key]=dict(gain=abs(z),phase_deg=float(np.angle(z,deg=True)),phase_equivalent_delay_ms=float(-np.angle(z)/(2*np.pi*f)*1000))
    out['frequency_hz']=f;out['bandwidth_hz']=10;out['step_ms']=1
    out['additional_zero_order_hold_phase_deg']={'100Hz':-360*f*.005,'250Hz':-360*f*.002}
    out['assumed_sim_4ms_transport_phase_deg']=-360*f*.004
    return out

def trial(label, folder,net=None):
    folder=Path(folder);report=js(folder/'report.json')
    files=sorted((ROOT/folder).glob('rig-*.jsonl*'));assert len(files)==1
    rows=[json.loads(line) for line in read(files[0].relative_to(ROOT)).splitlines()]
    states=[r['state'] for r in rows if r['type']=='state']; lookup={s['unwrapped_tick']:s for s in states}
    start=next(r for r in rows if r['type']=='policy_start');end=next(r for r in rows if r['type']=='policy_end')
    requests=[r for r in rows if r['type']=='action_request' and start['host_monotonic_ns']<=r['host_monotonic_ns']<=end['host_monotonic_ns']]
    active=[r['state'] for r in rows if r['type']=='state' and start['host_monotonic_ns']<=r['host_monotonic_ns']<=end['host_monotonic_ns'] and r['state']['flags']&2]
    assert active and requests
    t0=active[0]['unwrapped_us']/1e6
    transitions=[r for r in rows if r['type']=='policy_transition']
    balance_ns=next((r['board_ns'] for r in transitions if r['mode']=='balance'),None)
    params=report.get('parameters') or next((r['controller_parameters'] for r in rows if r['type']=='host_controller'),None)
    if params is None:
        # Current timed report stores its immutable preflight readback here.
        params=report.get('preflight',{}).get('parameters')
    if params is None:
        params=js(Path('training/candidates/balance-20261021-confidence/actor.json'))['executor_parameters']
    p=ControllerParameters(**params);auto=gains(p);bal=gains(p,upright=True)
    observed=[];replay=[];diff=[];filtered_delta=[];native_error=[];request_times=[];receipt_send=[];detail=[]
    for r in requests:
        q=r['request'];s=lookup[q['observation_sequence']];assert s['flags']&1 and s['flags']&4
        now=s['unwrapped_us']/1e6-t0;u=q['acceleration_m_s2']
        aauto=balance(auto,s['angle_hat'],s['omega'],s['x'],s['velocity'])
        abal=balance(bal,s['angle_hat'],s['omega'],s['x'],s['velocity'])
        row=dict(t_s=now,theta_deg=math.degrees(s['theta']),filtered_deg=math.degrees(s['angle_hat']),omega=s['omega'],x=s['x'],v=s['velocity'],a=s['acceleration'],accepted_demand=s['demand'],request=u,auto_filtered=aauto,bal_filtered=abal,brake=s['brake_direction'])
        observed.append(s);request_times.append(q['issued_at_ns']);receipt_send.append((r['host_monotonic_ns']-s['received_ns'])/1e6)
        if net:
            un=net.predict_encoded(enc(s));uf=net.predict_encoded(enc(s,True));diff.append(un-u);filtered_delta.append(uf-un);row.update(actor_raw=un,actor_filtered_counterfactual=uf)
        elif balance_ns is not None and q['issued_at_ns']>=balance_ns:
            vmax=min(p.vmax,p.vmax_b);lo=settled_velocity_accel(s['velocity'],s['acceleration'],-vmax,max(p.amax_s,p.amax_b),p.jmax,.004);hi=settled_velocity_accel(s['velocity'],s['acceleration'],vmax,max(p.amax_s,p.amax_b),p.jmax,.004)
            native_error.append(max(lo,min(hi,max(-p.amax_b,min(p.amax_b,aauto))))-u)
        detail.append(row)
    ts=np.asarray([d['t_s'] for d in detail]);theta=np.asarray([d['theta_deg'] for d in detail])
    def window(lo,hi):
        d=[r for r in detail if lo-1e-7<=r['t_s']<hi-1e-7]
        if not d:return None
        t=np.asarray([r['t_s'] for r in d]); aa=np.asarray([r['a'] for r in d]);uu=np.asarray([r['accepted_demand']for r in d])
        return dict(interval_s=[lo,hi],samples=len(d),theta_deg=stats([r['theta_deg']for r in d]),request=stats([r['request']for r in d]),auto_filtered_counterfactual=stats([r['auto_filtered']for r in d]),bal_filtered_counterfactual=stats([r['bal_filtered']for r in d]),raw_minus_filtered_deg=stats([r['theta_deg']-r['filtered_deg']for r in d]),accepted_demand_minus_governed=stats(uu-aa),fraction_governor_mismatch_over_0p2=float(np.mean(abs(uu-aa)>.2)),fraction_10ms_accel_slopes_at_jerk_limit=float(np.mean(abs(np.diff(aa)/np.diff(t))>=p.jmax*.995)) if len(t)>1 else 0.,theta_peak=spectral(t,np.asarray([r['theta_deg']for r in d])))
    bstart=None if balance_ns is None else balance_ns/1e9-t0
    result=dict(label=label,source=str(folder),parameters=params,policy_start=start,policy_end=end,requests=len(requests),active_span_s=(active[-1]['unwrapped_us']-active[0]['unwrapped_us'])/1e6,first_states=active[:5],transitions=transitions,board_request_intervals_ms=stats(np.diff(request_times)/1e6),host_receipt_to_request_record_ms=stats(receipt_send),replay_minus_recorded=stats(diff),actor_filtered_minus_raw_counterfactual=stats(filtered_delta),auto_balance_equation_minus_recorded=stats(native_error),faults=sorted({s['fault']for s in active}),startup_quarters=[window(i*.25,(i+1)*.25)for i in range(4)],first_second=window(0,1),balance_window=None if bstart is None else window(bstart,ts[-1]+.001),first_abs_5deg_s=next((r['t_s']for r in detail if abs(r['theta_deg'])>5),None),first_brake_s=next((r['t_s']for r in detail if r['brake']),None))
    if net:assert max(abs(x)for x in diff)<1e-5
    if native_error:assert max(abs(x)for x in native_error)<1e-4
    return result,detail

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);args=ap.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    confidence,cd=load_actor('balance-20261021-confidence');centered,sd=load_actor('balance-20261021-centered')
    specs=[('original_hold','runs/policy-confidence-20261021/hardware-live/balance47-run10-gil1-01',confidence),('original_startup_failure','runs/policy-confidence-20261021/hardware-live/balance47-run25-rr10-ref553-01',confidence),('centered_startup_failure','runs/policy-confidence-20261021/hardware-live/centered-run25-rr10-01',centered),('python_auto_success','evidence/python-control-id-20261016/hardware/runs/auto-1792181675003538876',None)]
    reports=[];details={}
    for label,folder,net in specs:
        r,d=trial(label,folder,net);reports.append(r);details[label]=d
    model=js(Path('training/profiles/rl-encoder-20261021/model.json'));config=model['simulation_config'];L=config['effective_length_m'];mass=config['pole_mass_kg'];I=.75*mass*L*L
    native=js(Path('evidence/python-control-id-20261016/reliability-audit/native-1792178943322637321-compact.json'))
    sources=['control/policy.py','control/reference.py','control/motion.py','control/parameters.py','policies/executor_feedback.py','policies/neural.py','policies/numeric_backend.py','policies/rig_observation.py','rig/policy.py','rig/client.py','sim/rig_gym_env.py','sim/executor.py','sim/backend.py','sim/model.py']
    for p in sources:read(Path('src/cartpole_sdk')/p)
    for p in ['firmware/teensy_executor/swing_controller.h','firmware/teensy_executor/cart_motion.h','firmware/teensy_executor/executor_core.h','docs/python-control-20261016.md']:read(Path(p))
    report=dict(schema='cartpole-transfer-audit-v1',hardware_activity=False,production_edits=False,actors={'confidence':cd,'centered':sd},observer_sinusoidal_response=observer_response(),trials=reports,native_historical=dict(source_manifest=native['source_manifest'],parameters=native['report']['parameters'],active_count=native['active_count'],balance_count=native['balance_count'],balance_stats=native['balance_stats']),model=dict(config=config,pivot_inertia_kg_m2=I,small_speed_damping_per_s=(config['hinge_damping']+config['hinge_coulomb_friction_nm']/config['hinge_friction_velocity_scale_rad_s'])/I,large_speed_viscous_damping_per_s=config['hinge_damping']/I,limitations=model['limitations']),limits=['All additional feedback values are offline counterfactuals on the recorded trajectory, not predicted closed-loop outcomes.','Raw angle is quantized magnetic angle; velocity/acceleration/position are commanded/step state, not independent physical tracking.','An FFT peak of a growing transient is descriptive, not an identified plant mode.','Receipt-to-request timestamps include inference and post-write logging; neither measures one-way board transport latency.','Unrecorded 1 ms intermediate governor/observer samples cannot be reconstructed exactly from 100/250 Hz telemetry.','No reserved simulation poses, training, fitting, hardware, or network used.'])
    import matplotlib;matplotlib.use('Agg');import matplotlib.pyplot as plt
    fig,axs=plt.subplots(3,2,figsize=(12,9),sharex='col')
    for col,label in enumerate(['centered_startup_failure','python_auto_success']):
        data=details[label];start=0 if col==0 else reports[-1]['balance_window']['interval_s'][0]+1
        subset=[d for d in data if start<=d['t_s']<=start+1.]
        t=[d['t_s']-start for d in subset]
        axs[0,col].plot(t,[d['theta_deg']for d in subset],label='raw encoder');axs[0,col].plot(t,[d['filtered_deg']for d in subset],label='MCU filtered');axs[0,col].legend();axs[0,col].set_title(label)
        axs[1,col].plot(t,[d['request']for d in subset],label='requested');axs[1,col].plot(t,[d['a']for d in subset],label='governed');axs[1,col].plot(t,[d['auto_filtered']for d in subset],label='AUTO feedback counterfactual',alpha=.6);axs[1,col].legend(fontsize=7)
        axs[2,col].plot(t,[d['omega']for d in subset],label='MCU omega');axs[2,col].legend();axs[2,col].set_xlabel('seconds within shown window')
    for ax,label in zip(axs[:,0],['angle (deg)','acceleration (m/s²)','angular rate (rad/s)']):ax.set_ylabel(label)
    for ax in axs.flat:ax.grid(alpha=.2)
    fig.suptitle('Recorded dynamics; windows are illustrative and not matched experiments');fig.tight_layout();fig.savefig(args.output/'comparison.png',dpi=150);plt.close(fig)
    (args.output/'detail.json').write_text(json.dumps(details,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n')
    report['inputs']=INPUTS;report['script_sha256']=sha256(Path(__file__).read_bytes()).hexdigest();report['output_sha256']={name:sha256((args.output/name).read_bytes()).hexdigest()for name in ['detail.json','comparison.png']}
    (args.output/'analysis.json').write_text(json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+'\n')
    print(json.dumps({'output':str(args.output),'verified_actor_commands':sum(r['replay_minus_recorded']['n']for r in reports if r['replay_minus_recorded']),'verified_python_balance_commands':reports[-1]['auto_balance_equation_minus_recorded']['n'],'finite_json':True}))
if __name__=='__main__':main()
