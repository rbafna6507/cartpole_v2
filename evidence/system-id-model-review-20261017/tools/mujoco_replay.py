#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=1.26,<3", "scipy==1.16.3", "mujoco==3.15.0", "matplotlib>=3.8,<4"]
# ///
"""Replay a frozen passive candidate in MuJoCo with the cart physically fixed.

Verification harness only: no production SimulationConfig export, no RL policy,
no hardware. The dry-friction torque is applied each physics tick; the MJCF by
itself contains only viscous damping and must not be loaded as a complete model.
"""
import argparse,gzip,hashlib,json,math,sys
from pathlib import Path
import numpy as np
import mujoco
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'src'))
from cartpole_sdk.identification import workflow,passive
from dynamics import initial_state,ode_solution,metrics


def model_for(c,dt):
    magnitude=math.hypot(c[0],c[2]);length=1.5*9.81/magnitude;mass=.02275;inertia=mass*length**2/3;center_inertia=mass*length**2/12
    xml=f'''<mujoco model="experimental_fixed_cart_passive_candidate">
<compiler angle="radian" inertiafromgeom="false"/>
<option timestep="{dt:.17g}" gravity="0 0 -9.81" integrator="Euler"><flag eulerdamp="disable" autoreset="disable"/></option>
<worldbody><body name="pole"><joint name="pole_hinge" type="hinge" axis="0 1 0" damping="{c[1]*inertia:.17g}" limited="false"/>
<inertial pos="0 0 {length/2:.17g}" mass="{mass:.17g}" diaginertia="{center_inertia:.17g} {center_inertia:.17g} {center_inertia*1e-6:.17g}"/>
<geom type="capsule" fromto="0 0 0 0 0 {length:.17g}" size=".004" contype="0" conaffinity="0"/></body></worldbody></mujoco>'''
    return mujoco.MjModel.from_xml_string(xml),xml,inertia


def torque(c,inertia,omega):return -inertia*((c[3] if len(c)>3 else 0)*math.tanh(omega/.05)+(c[4] if len(c)>4 else 0)*omega*abs(omega))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--freeze',type=Path,required=True);p.add_argument('--source',type=Path,required=True);p.add_argument('--annotations',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--warmup',type=float,default=.5);p.add_argument('--dt',type=float,default=.001);a=p.parse_args()
    if a.output.exists():raise FileExistsError(a.output)
    if a.dt<=0 or a.dt>.002 or a.warmup<.1:raise ValueError('invalid numerical verification settings')
    freeze=workflow.read_json(a.freeze)
    for name,digest in freeze['method_hashes'].items():
        if hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest()!=digest:raise ValueError('frozen method changed: '+name)
    chosen=next(x for x in freeze['models'] if x['model']=='weak_coulomb');c=chosen['coefficients'];phase=math.atan2(c[2],c[0]);model,xml,inertia=model_for(c,a.dt)
    force_errors=[]
    for q in np.linspace(-math.pi,math.pi,13):
        for w in np.linspace(-12,12,9):
            data=mujoco.MjData(model);data.qpos[0]=q+phase;data.qvel[0]=w;data.qfrc_applied[0]=torque(c,inertia,w);mujoco.mj_forward(model,data)
            expected=c[0]*math.sin(q)+c[2]*math.cos(q)-c[1]*w+torque(c,inertia,w)/inertia;force_errors.append(abs(data.qacc[0]-expected))
    assert max(force_errors)<1e-8,force_errors
    eps,identity=workflow.passive_episodes(str(a.source),a.annotations);parts=passive.segments(eps,dict(passive.DEFAULT_GATES,window_s=.35));rows=[];measured_errors=[];ode_errors=[]
    for t,q,epid in parts:
        start=int(np.searchsorted(t,t[0]+a.warmup))
        if start+1>=len(t):raise ValueError('insufficient length after initialization')
        state=initial_state(t,q,start,c,'history_rawq:'+str(a.warmup));data=mujoco.MjData(model);data.qpos[0]=state[0]+phase;data.qvel[0]=state[1];pred=[state[0]]
        for j in range(start+1,len(t)):
            delta=t[j]-t[j-1];steps=math.ceil(delta/a.dt);model.opt.timestep=delta/steps
            for _ in range(steps):data.qfrc_applied[0]=torque(c,inertia,float(data.qvel[0]));mujoco.mj_step(model,data)
            pred.append(float(data.qpos[0]-phase))
        pred=np.array(pred);ode=ode_solution(t[start:],state,c)[0];wrap=lambda x:np.arctan2(np.sin(x),np.cos(x));me=wrap(pred[1:]-q[start+1:]);oe=wrap(pred[1:]-ode[1:]);measured_errors.extend(me);ode_errors.extend(oe)
        rows.append(dict(episode_id=epid[1],initial_state=state.tolist(),t=t[start:].tolist(),observed=q[start:].tolist(),mujoco=pred.tolist(),ode=ode.tolist(),measured_error=metrics(me),ode_error=metrics(oe)))
    parity=metrics(ode_errors);assert parity['rms_deg']<.5 and max(abs(np.rad2deg(ode_errors)))<1.,parity
    report=dict(scope='Fixed-cart passive MuJoCo verification only; not production export or hardware-RL admission',accepted=False,source_identity=identity,freeze_sha256=hashlib.sha256(a.freeze.read_bytes()).hexdigest(),coefficients=c,initialization_history_s=a.warmup,physics_max_step_s=a.dt,raw_encoder_phase_mapping_rad=phase,phase_mapping_is_absolute_calibration=False,assumed_mass_kg=.02275,inertia_kg_m2=inertia,torque_law='-I * [c*tanh(omega/0.05) + d*omega*abs(omega)] applied at every tick',mujoco_version=mujoco.__version__,force_equation_max_error_rad_s2=max(force_errors),measured_error=metrics(measured_errors),ode_parity=parity,ode_max_difference_deg=float(max(abs(np.rad2deg(ode_errors)))),episodes=rows,
        limitations=['Cart is fixed; no actuator, rail, action latency or driven dynamics are validated.','MJCF alone omits the per-tick dry torque applied by this script.','Initial history is excluded from scoring and later observations never update the trajectory.','Source pose/camera qualification is reported in the frozen evaluation; this numerical check does not override failures.'])
    a.output.mkdir(parents=True);(a.output/'candidate.xml').write_text(xml);(a.output/'report.json.gz').write_bytes(gzip.compress(json.dumps(report,indent=2,allow_nan=False).encode(),mtime=0));workflow.write_json(a.output/'summary.json',{k:v for k,v in report.items() if k!='episodes'})
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(math.ceil(len(rows)/2),2,figsize=(13,3*math.ceil(len(rows)/2)),layout='constrained',squeeze=False)
    for ax,row in zip(axes.flat,rows):
        t=np.array(row['t']);q=np.array(row['observed']);baseline=identity['passive_baseline']['encoder']['raw_angle_rad'];branch=baseline+2*np.pi*round((np.median(q)-baseline)/(2*np.pi));ax.plot(t-t[0],np.rad2deg(q-branch),lw=1,label='Recorded encoder');ax.plot(t-t[0],np.rad2deg(np.array(row['mujoco'])-branch),lw=1,label='MuJoCo candidate');ax.set_title(f"{row['episode_id']}: RMS {row['measured_error']['rms_deg']:.2f}°");ax.grid(alpha=.2);ax.set_xlabel('Seconds after initialization');ax.set_ylabel('Angle from recorded hanging (degrees)')
    for ax in list(axes.flat)[len(rows):]:ax.set_visible(False)
    axes.flat[0].legend(fontsize=8);fig.suptitle(f"Fixed-cart MuJoCo candidate; no refit\n{a.warmup:g}s causal initialization; continuous prediction RMS {report['measured_error']['rms_deg']:.2f}°\nExperimental replay, not model promotion");fig.savefig(a.output/'recorded-vs-mujoco.png',dpi=140)
    print(json.dumps({k:report[k] for k in ['measured_error','ode_parity','ode_max_difference_deg','force_equation_max_error_rad_s2']},indent=2))
if __name__=='__main__':main()
