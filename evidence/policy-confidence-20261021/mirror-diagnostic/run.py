#!/usr/bin/env python3
"""Bounded frozen-actor mirror diagnostic. No training, export, or hardware.

Run with PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
MKL_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1
.venv/bin/python evidence/policy-confidence-20261021/mirror-diagnostic/run.py
An existing result directory is never overwritten.
"""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
import shutil
import time
import zipfile

import numpy as np
import torch

from cartpole_sdk.learning import robust_swing, transfer_checks
from cartpole_sdk.learning.diagnostics import _source_snapshot, preserved_rng
from cartpole_sdk.learning.error_training import _weights_hash
from cartpole_sdk.learning.ppo import TrainingEnv, _write_new, experiment_identity
from cartpole_sdk.learning.projected_ppo import EquilibriumPPO

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
OUT=ROOT/'runs/policy-confidence-20261021/mirror-diagnostic'
RUN=ROOT/'runs/policy-confidence-20261021/joint/ppo-seed11'
SEEDS=(95000,95001,95002,95003)
STARTS=('hanging','upright')
FLIPS=(0,1,2,4,5,6)
SECONDS=25.


def hashfile(path):return sha256(Path(path).read_bytes()).hexdigest()


def sources():
    return dict(driver_sha256=hashfile(__file__),robust=robust_swing.source_identity(),
        evaluator=transfer_checks.source_identity())


def mirror(observation):
    changed={key:np.array(value,copy=True) for key,value in observation.items()}
    changed['state'][...,list(FLIPS)]*=-1
    return changed


class OddPredictor:
    def __init__(self,model):self.model=model
    def predict(self,observation,deterministic=True):
        if not deterministic:raise ValueError('frozen deterministic diagnostic only')
        reflected=mirror(observation)
        batch={key:np.stack((observation[key],reflected[key])) for key in observation}
        tensor,_=self.model.policy.obs_to_tensor(batch)
        with torch.no_grad():
            means=self.model.policy.get_distribution(tensor).distribution.mean.flatten()
            value=torch.clamp(.5*(means[0]-means[1]),-1.,1.)
        return np.array([float(value)],dtype=np.float32),None


def folded_audit(model,observations):
    """Algebra check in float64; this is not an accepted/deployable actor export."""
    layers=robust_swing._actor_layers(model)
    w1,w2,w3=[layer.weight.detach().cpu().numpy().astype(np.float64) for layer in layers]
    b1,b2,b3=[layer.bias.detach().cpu().numpy().astype(np.float64) for layer in layers]
    sign=np.ones(21);sign[7+np.array(FLIPS)]=-1.
    fw1=np.vstack((w1,w1*sign));fb1=np.tile(b1,2)
    fw2=np.zeros((128,128));fw2[:64,:64]=w2;fw2[64:,64:]=w2;fb2=np.tile(b2,2)
    fw3=np.hstack((.5*w3,-.5*w3));fb3=np.zeros(1)
    max_raw=max_odd=0.;even_squares=[]
    for offset in range(0,len(observations),512):
        batch=observations[offset:offset+512]
        x=np.asarray([[float(v) for key in ('age_s','state','valid') for v in obs[key]] for obs in batch])
        def raw(values):return np.tanh(np.tanh(values@w1.T+b1)@w2.T+b2)@w3.T+b3
        original=raw(x);reflected=raw(x*sign);odd=.5*(original-reflected)
        def folded(values):return np.tanh(np.tanh(values@fw1.T+fb1)@fw2.T+fb2)@fw3.T+fb3
        actual=folded(x)
        max_raw=max(max_raw,float(np.max(np.abs(actual-odd))))
        max_odd=max(max_odd,float(np.max(np.abs(actual+folded(x*sign)))))
        even_squares.extend((.5*(original+reflected)).flatten()**2)
    return dict(compared_observations=len(observations),float64_fold_max_abs_mean_error=max_raw,
        float64_fold_max_abs_oddness_error=max_odd,original_even_component_rms_normalized=float(np.sqrt(np.mean(even_squares))),
        exact_real_arithmetic=True,architecture=[21,128,128,1],
        construction=dict(input='x=[age_s,state,valid], D diagonal with -1 at state indices0,1,2,4,5,6; +1 elsewhere',
            first='W1_new=[W1;W1 D], b1_new=[b1;b1]',second='W2_new=blockdiag(W2,W2), b2_new=[b2;b2]',
            output='W3_new=0.5*[W3,-W3], b3_new=0; clip once after final mean, then multiply physical action scale'),
        interface='Same21 observation features and one normalized action; two64 branches represented as128-wide layers.',
        current_numeric_contract='Current validate_actor and export_actor require21-64-64-1; a128-wide artifact would be rejected. Supporting it needs deliberate schema/shape-validation/export/backend work and fresh parity. No production interface or runtime was changed.',
        numeric_exported=False,hardware_accepted=False)


def main():
    torch.set_num_threads(1);torch.set_num_interop_threads(1)
    recipe_bytes=(RUN/'recipe.json').read_bytes();report_bytes=(RUN/'report.json').read_bytes()
    recipe=json.loads(recipe_bytes);running=json.loads(report_bytes)
    if sha256(recipe_bytes).hexdigest()!=running['recipe_sha256']:raise ValueError('run recipe hash mismatch')
    if hashfile(RUN/'source.zip')!=running['source_zip_sha256']:raise ValueError('run source archive hash mismatch')
    selected=next(row for row in running['checkpoints'] if row['step']==0)
    checkpoint=RUN/selected['path']
    if checkpoint.parent.resolve()!=(RUN/'checkpoints').resolve() or hashfile(checkpoint)!=selected['sha256']:raise ValueError('checkpoint binding mismatch')
    if recipe['source']['robust']!=robust_swing.source_identity():raise ValueError('current runtime differs from frozen run')
    with zipfile.ZipFile(RUN/'source.zip') as archive:
        if sha256(archive.read('confidence/run-joint-stage.py')).hexdigest()!=recipe['source']['driver']:raise ValueError('archived driver mismatch')
    if any(hashfile(path)!=pin for path,pin in recipe['inputs'].items()):raise ValueError('profile input changed')
    exp=deepcopy(recipe['experiment'])
    if experiment_identity(exp)!=recipe['experiment_sha256'] or exp['executor_parameters']['bw']!=10. or exp['simulation_config']['max_steps']!=2500:raise ValueError('frozen profile mismatch')
    low,high=recipe['protocol']['training_seeds']
    if set(SEEDS)&(set(range(low,high+1))|set(recipe['protocol']['future_confirmation_seeds'])):raise ValueError('training or holdout overlap')
    identity=sources()
    protocol=dict(schema='cartpole-mirror-diagnostic-v1',declared_at_utc=datetime.now(timezone.utc).isoformat(),
        question='Does an odd projection of the frozen initial actor preserve or improve nominal development-pose swing capture?',
        checkpoint=dict(path=str(checkpoint),sha256=selected['sha256'],actor_weights_sha256=selected['actor_weights_sha256'],step=0),
        source_run=str(RUN),source_recipe_sha256=sha256(recipe_bytes).hexdigest(),
        source_running_report_snapshot_sha256=sha256(report_bytes).hexdigest(),source_run_completed_at_snapshot=running['completed'],
        source_archive_sha256=running['source_zip_sha256'],source=identity,experiment=exp,
        experiment_sha256=recipe['experiment_sha256'],input_files=recipe['inputs'],
        seeds=list(SEEDS),previously_inspected_seeds=[95000,95001],newly_inspected_seeds=[95002,95003],all_seeds_inspected_after_run=list(SEEDS),
        seed_role='Development only, including previously inspected joint-development poses; no independent confirmation claim.',
        starts=list(STARTS),seconds=SECONDS,arms=['original','odd-raw-mean'],
        mirror=dict(state_sign_flip_indices=list(FLIPS),preserve=['state[3] cos(angle)','age_s','valid']),
        action_original='Original SB3 deterministic normalized action clip(f(obs),-1,1)',
        action_odd='clip(0.5*(f(obs)-f(Mobs)),-1,1), where f is UNCLIPPED Gaussian mean; multiply env action scale once',
        evaluation='Nominal frozen profile through existing TrainingEnv and transfer_checks._episode; no randomization, same seeds per arm.',
        success='Complete2500 decisions with no fault and final5s continuous abs(theta)<0.15rad,abs(omega)<1rad/s,abs(x)<0.12m.',
        metrics=['hold count','fault count','first1s capture','longest dwell','max cart displacement','complete-final-window x/theta RMS','trace SHA256','algebraic fold error'],
        incomplete_tail='Null when final_window_complete is false or the final-time window is empty; never mean(empty) or NaN.',
        worker_count=1,torch_cpu_threads=1,training_performed=False,hardware_accepted=False,deployable=False,
        limitations=['Small development-pose diagnostic; no training or learned improvement claim.','Nominal modeled symmetry does not establish physical hardware symmetry or transfer.','Same-seed sensor noise is not explicitly mirrored between separate closed-loop trajectories.','No96000+confirmation poses inspected.','Odd projection may remove useful asymmetric kick/escape behavior near hanging symmetry.'])
    OUT.mkdir(parents=True,exist_ok=False);(OUT/'traces').mkdir();(OUT/'frozen-inputs').mkdir()
    _write_new(HERE/'protocol.json',protocol);_write_new(OUT/'protocol.json',protocol)
    (OUT/'source-recipe.json').write_bytes(recipe_bytes);(OUT/'source-running-report-snapshot.json').write_bytes(report_bytes)
    shutil.copy2(__file__,OUT/'run.py')
    for index,path in enumerate(recipe['inputs']):shutil.copy2(path,OUT/'frozen-inputs'/f'{index}-{Path(path).name}')
    _source_snapshot(OUT/'source.zip')
    with zipfile.ZipFile(OUT/'source.zip','a',zipfile.ZIP_DEFLATED) as archive:archive.write(__file__,'diagnostic/run.py')
    print(json.dumps(dict(event='predeclared',seeds=SEEDS,protocol_sha256=hashfile(OUT/'protocol.json'))),flush=True)
    model=EquilibriumPPO.load(checkpoint,device='cpu');model.policy.set_training_mode(False)
    weights=_weights_hash(model);actor_weights=robust_swing.actor_weights_hash(model)
    if actor_weights!=selected['actor_weights_sha256']:raise ValueError('loaded actor differs from frozen checkpoint binding')
    began=time.monotonic();episodes=[];observations=[]
    with preserved_rng():
        for arm,predictor in [('original',model),('odd-raw-mean',OddPredictor(model))]:
            env=TrainingEnv(exp,SEEDS,randomization=None)
            try:
                for seed in SEEDS:
                    for start in STARTS:
                        scenario=dict(name=arm,expected='task_success',angle_offset_rad=0.,observation_override={},randomization=None)
                        result=transfer_checks._episode(predictor,env,seed=seed,start=start,scenario=scenario,root=OUT)
                        rows=[json.loads(line) for line in (OUT/result['trace_path']).open()]
                        tail=[row for row in rows if row['physical_time_advanced'] and row['elapsed_since_reset_s']>SECONDS-5.]
                        complete=bool(tail and result['final_window_complete'])
                        result['final_window_x_rms_m']=float(np.sqrt(np.mean([row['ground_truth_after']['x']**2 for row in tail]))) if complete else None
                        result['tail_theta_rms_deg']=float(np.sqrt(np.mean([row['ground_truth_after']['theta']**2 for row in tail])))*180/math.pi if complete else None
                        result['final_window_samples']=len(tail) if complete else 0
                        result['rail_margin_m']=exp['simulation_config']['rail_half_m']-result['max_abs_x_m']
                        episodes.append(result);observations.extend(row['actor_observation'] for row in rows)
                        _write_new(OUT/f'episode-{arm}-{start}-{seed}.json',result)
                        print(json.dumps(dict(event='episode',arm=arm,seed=seed,start=start,hold=result['hold_success'],fault=result['fault_reason'],capture_s=result['first_one_second_capture_s'],longest_dwell_s=result['longest_balance_dwell_s'])),flush=True)
            finally:env.close()
    audit=folded_audit(model,observations)
    if audit['float64_fold_max_abs_mean_error']>1e-12 or audit['float64_fold_max_abs_oddness_error']>1e-12:raise ValueError('algebraic mirror fold mismatch')
    if sources()!=identity or _weights_hash(model)!=weights or hashfile(checkpoint)!=selected['sha256']:raise ValueError('evaluation source or weights changed')
    if hashfile(RUN/'recipe.json')!=protocol['source_recipe_sha256'] or any(hashfile(path)!=pin for path,pin in recipe['inputs'].items()):raise ValueError('frozen source inputs changed')
    summaries=[]
    for arm in protocol['arms']:
        for start in STARTS:
            rows=[row for row in episodes if row['scenario']==arm and row['start']==start]
            captures=[row['first_one_second_capture_s'] for row in rows if row['first_one_second_capture_s'] is not None]
            summaries.append(dict(arm=arm,start=start,episodes=len(rows),holds=sum(row['hold_success'] for row in rows),faults=sum(row['fault_reason'] is not None for row in rows),captures=len(captures),
                mean_capture_s=float(np.mean(captures)) if captures else None,mean_longest_dwell_s=float(np.mean([row['longest_balance_dwell_s'] for row in rows])),
                worst_max_abs_x_m=max(row['max_abs_x_m'] for row in rows),mean_tail_x_rms_m=float(np.mean([row['final_window_x_rms_m'] for row in rows])) if all(row['final_window_x_rms_m'] is not None for row in rows) else None,
                mean_tail_theta_rms_deg=float(np.mean([row['tail_theta_rms_deg'] for row in rows])) if all(row['tail_theta_rms_deg'] is not None for row in rows) else None))
    report=dict(schema='cartpole-mirror-diagnostic-report-v1',completed=True,training_performed=False,hardware_accepted=False,deployable=False,
        protocol_sha256=hashfile(OUT/'protocol.json'),source_zip_sha256=hashfile(OUT/'source.zip'),source=identity,
        checkpoint=protocol['checkpoint'],in_memory_weights_sha256=weights,actor_weights_sha256=actor_weights,experiment_sha256=recipe['experiment_sha256'],
        source_and_weights_unchanged=True,wall_seconds=time.monotonic()-began,episodes=episodes,summary=summaries,folded_architecture=audit,
        limitations=protocol['limitations'])
    _write_new(OUT/'report.json',report);_write_new(HERE/'report.json',report)
    print(json.dumps(dict(event='complete',summary=summaries,folded_architecture=audit),indent=2),flush=True)


if __name__=='__main__':main()
