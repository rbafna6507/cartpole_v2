"""Compare an unchanged MuJoCo passive candidate with annotated heldout data."""
import argparse
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import numpy as np
from cartpole_sdk.sim.backend import MujocoBackend
from cartpole_sdk.sim.config import SimulationConfig


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--data',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    spec=importlib.util.spec_from_file_location('frozen_evaluator',a.root/'analysis/heldout/evaluate_passive.py')
    evaluator=importlib.util.module_from_spec(spec);spec.loader.exec_module(evaluator)
    fitter,training,freeze=evaluator.verify_freeze(a.root/'analysis')
    annotation=json.loads((a.root/'analysis/heldout/manual-ringdown-heldout-01-annotations.json').read_text())
    evaluator.validate_annotations(annotation)
    raw=a.data.read_bytes();assert hashlib.sha256(raw).hexdigest()==annotation['source_export_sha256']
    data=json.loads(gzip.decompress(raw));s,_=evaluator.canonical_states(data['states'])
    assert data['report']['raw_log_sha256']==annotation['raw_recording_sha256']
    assert annotation['raw_recording_sha256'] not in training['magnetic_reports']['viscous']['provenance']['training_run_ids']
    t=(s[:,0]-s[0,0])/1e6;q=np.unwrap(s[:,3])
    params=freeze['candidate_parameters'];bias=params['angle_offset_rad']
    config_path=a.root/'mujoco-passive-candidate/model-config.json'
    config=SimulationConfig(**json.loads(config_path.read_text()))
    assert config.effective_length_m==params['effective_length_m']
    assert abs(config.hinge_damping-.75*config.pole_mass_kg*config.effective_length_m**2*params['angular_damping_per_s'])<1e-15
    cfg=training['magnetic_reports']['viscous']['provenance']['config']
    windows=[];all_errors=[];per_episode=[]
    for ep in annotation['episodes']:
        lo,hi=ep['board_relative_s'];ix=(t>=lo)&(t<=hi)
        episodes=[dict(run_id=annotation['raw_recording_sha256'],episode_id=ep['episode_id'],t_s=t[ix].tolist(),theta_rad=q[ix].tolist())]
        errors=[]
        for tt,qq,identity in fitter.segments(episodes,cfg):
            i=max(10,int(np.searchsorted(tt,tt[0]+.1)))
            while i+8<len(tt):
                end=int(np.searchsorted(tt,tt[i]+cfg['prediction_horizon_s'],side='right'))
                if tt[end-1]-tt[i]<.9*cfg['prediction_horizon_s']:break
                omega=float(np.polyfit(tt[i-10:i+1]-tt[i],qq[i-10:i+1],2)[-2])
                sim=MujocoBackend(config);sim.reset(state=(0.,0.,float(qq[i]-bias),omega))
                readings=[];max_a=max_force=0.;saturated=False
                for j in range(i+1,end):
                    delta=tt[j]-tt[j-1];steps=round(delta/.001)
                    assert steps>0 and abs(steps*.001-delta)<1e-7,'non-1ms board grid'
                    for _ in range(steps):
                        sim.step(None)
                        max_a=max(max_a,abs(sim.diagnostics.achieved_acceleration_m_s2))
                        max_force=max(max_force,abs(sim.diagnostics.applied_force_n))
                        saturated|=sim.diagnostics.force_saturated
                    prediction=sim.ground_truth.theta+bias
                    error=math.atan2(math.sin(prediction-qq[j]),math.cos(prediction-qq[j]))
                    # Preserve a continuous display branch near the measurement.
                    readings.append([float(tt[j]),float(qq[j]),float(qq[j]+error),error])
                    errors.append(error)
                sim.close()
                windows.append(dict(episode=ep['episode_id'],start_s=float(tt[i]),initial_omega=omega,
                    maximum_cart_acceleration=max_a,maximum_force=max_force,force_saturated=saturated,readings=readings))
                i=end
        e=np.array(errors);all_errors.extend(errors)
        per_episode.append(dict(episode=ep['episode_id'],samples=len(e),rmse_rad=float(np.sqrt(np.mean(e*e))),p95_rad=float(np.quantile(abs(e),.95))))
    e=np.array(all_errors);rmse=float(np.sqrt(np.mean(e*e)));p95=float(np.quantile(abs(e),.95))
    result=dict(status='MuJoCo heldout comparison; narrow passive-domain evidence only',
        coefficients_refitted=False,local_phase_offset_rad=bias,windows=len(windows),samples=len(e),
        rmse_rad=rmse,p95_rad=p95,aggregate_prediction_checks_pass=rmse<=cfg['max_prediction_rmse_rad'] and p95<=cfg['max_prediction_p95_rad'],
        physical_model_globally_validated=False,
        unsaturated=all(not w['force_saturated'] for w in windows),maximum_cart_acceleration=max(w['maximum_cart_acceleration'] for w in windows),
        provenance=dict(training_freeze_sha256=evaluator.FREEZE_SHA256,data_sha256=hashlib.sha256(raw).hexdigest(),
            annotation_sha256=evaluator.sha(a.root/'analysis/heldout/manual-ringdown-heldout-01-annotations.json'),
            model_config_sha256=evaluator.sha(config_path),script_sha256=evaluator.sha(__file__)),
        per_episode=per_episode,reading_columns=['time_s','measured_raw_angle_rad','predicted_raw_angle_rad','error_rad'],predictions=windows,
        limitations=['Local gravity-phase offset is not a global encoder correction.',
                    'Each0.5second window resets angle/rate from past observations; not a full-release open-loop test.',
                    'Cart is constrained by zero acceleration intent; masses, forces and driven response remain assumed.',
                    'Per-episode errors must be reported alongside aggregate gates.'])
    assert result['unsaturated'] and result['maximum_cart_acceleration']<1e-9
    if a.output.exists():raise ValueError('output already exists')
    a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('windows','samples','rmse_rad','p95_rad','aggregate_prediction_checks_pass','per_episode')}))


if __name__=='__main__':main()
