#!/usr/bin/env python3
"""Frozen actor exploration diagnostic: sixteen nominal episodes, no learning."""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json, math, os, shutil, time, zipfile
from pathlib import Path
import numpy as np
import torch
from cartpole_sdk.learning import robust_swing
from cartpole_sdk.learning.diagnostics import _source_snapshot, preserved_rng
from cartpole_sdk.learning.error_training import _weights_hash
from cartpole_sdk.learning.ppo import TrainingEnv, _write_new, experiment_identity
from cartpole_sdk.learning.projected_ppo import EquilibriumPPO
ROOT=Path('/Users/rbafna/projects/cartpole_v2')
HERE=Path(__file__).resolve().parent
OUT=ROOT/'runs/policy-confidence-20261021/exploration-diagnostic'
RUN=ROOT/'runs/policy-confidence-20261021/joint/ppo-seed11'
POSES=(95000,95001)
STARTS=('hanging','upright')
STDS=(0.,.01,.02,.05)
def digest(path):return sha256(Path(path).read_bytes()).hexdigest()
def sources():return dict(robust=robust_swing.source_identity(),driver_sha256=digest(__file__))
def seed_for(pose,start):return int(np.random.SeedSequence([20261021,pose,STARTS.index(start),4242]).generate_state(1)[0])
def main():
    torch.set_num_threads(1);torch.set_num_interop_threads(1)
    recipe_bytes=(RUN/'recipe.json').read_bytes();report_bytes=(RUN/'report.json').read_bytes()
    recipe=json.loads(recipe_bytes);report=json.loads(report_bytes)
    assert sha256(recipe_bytes).hexdigest()==report['recipe_sha256']
    assert digest(RUN/'source.zip')==report['source_zip_sha256']
    selected=next(c for c in report['checkpoints'] if c['step']==0)
    checkpoint=RUN/selected['path']
    assert checkpoint.parent.resolve()==(RUN/'checkpoints').resolve() and digest(checkpoint)==selected['sha256']
    assert recipe['source']['robust']==robust_swing.source_identity()
    with zipfile.ZipFile(RUN/'source.zip') as archive:
        assert sha256(archive.read('confidence/run-joint-stage.py')).hexdigest()==recipe['source']['driver']
    assert all(digest(p)==pin for p,pin in recipe['inputs'].items())
    exp=deepcopy(recipe['experiment']);assert experiment_identity(exp)==recipe['experiment_sha256']
    assert exp['simulation_config']['max_steps']==2500 and exp['executor_parameters']['bw']==10
    assert exp['executor_parameters']['jmax']==150 and exp['simulation_config']['max_acceleration_m_s2']==25
    assert not(set(POSES)&set(recipe['protocol']['future_confirmation_seeds']))
    identity=sources()
    protocol=dict(schema='cartpole-frozen-exploration-diagnostic-v1',declared_at_utc=datetime.now(timezone.utc).isoformat(),
        question='Does Gaussian exploration with normalized std .05 degrade frozen-actor capture or balance compared with mean actions and smaller std?',
        source_run=str(RUN),source_recipe_sha256=sha256(recipe_bytes).hexdigest(),source_report_snapshot_sha256=sha256(report_bytes).hexdigest(),
        source_archive_sha256=report['source_zip_sha256'],checkpoint=selected,checkpoint_path=str(checkpoint),source=identity,
        experiment=exp,experiment_sha256=recipe['experiment_sha256'],input_files=recipe['inputs'],
        conditions=[dict(normalized_std=s,raw_std_m_s2=s*25,deterministic=s==0) for s in STDS],
        pose_seeds=list(POSES),starts=list(STARTS),seconds=25,expected_episodes=16,expected_decisions=40000,
        seed_role='Already-inspected development poses only. No holdout or 96000+ poses.',
        action_semantics='Use actual SB3 policy.get_distribution(obs_tensor).get_actions(deterministic=std==0). For nonzero std set policy.log_std=log(std) in memory. Clip resulting normalized action to [-1,1] as SB3 BasePolicy.predict does, then TrainingEnv scales once by25. Deterministic condition leaves stored log_std unchanged but samples no noise.',
        rng_pairing='Reset Torch seed to numpy SeedSequence([20261021,pose_seed,start_index,4242]).generate_state(1)[0] before each episode; same seed across conditions for each pose/start. Environment is separately reset to the same episode seed. Stochastic trajectory pairing does not prove exact shared environmental RNG/noise after trajectories diverge.',
        rng_seeds=[dict(pose_seed=p,start=s,torch_seed=seed_for(p,s)) for p in POSES for s in STARTS],
        environment='Existing TrainingEnv, nominal current-run recipe, no domain randomization, reward_scale1.',
        success='Full2500 decisions without fault and final5s continuously abs(x)<.12m,abs(theta)<.15rad,abs(omega)<1rad/s.',
        metrics=['final hold','whole-horizon balanced fraction','longest dwell','first completed1s capture','total benchmark reward','mean benchmark reward','equivalent .01-scaled reward','raw command jitter','tail cart RMS'],
        worker_count=1,torch_cpu_threads=1,training_performed=False,hardware_accepted=False,deployable=False,
        limitations=['Only two common development poses per start and one stochastic stream per pose/start.','One frozen actor; no claim that lower exploration improves learned final policies.','Same RNG seeds do not make state trajectories or environment noise effects identical.','Raw Gaussian standard deviation is before normalized clipping and the unchanged jerk-limited governor.','No hardware or cloud; no source or policy files edited.'])
    OUT.mkdir(parents=True,exist_ok=False);(OUT/'traces').mkdir();(OUT/'frozen-inputs').mkdir()
    _write_new(HERE/'protocol.json',protocol);_write_new(OUT/'protocol.json',protocol)
    (OUT/'source-recipe.json').write_bytes(recipe_bytes);(OUT/'source-report-snapshot.json').write_bytes(report_bytes)
    shutil.copy2(__file__,OUT/'run.py');shutil.copy2(checkpoint,OUT/'checkpoint-step000000000.zip');shutil.copy2(RUN/'source.zip',OUT/'training-source.zip')
    for i,p in enumerate(recipe['inputs']):shutil.copy2(p,OUT/'frozen-inputs'/f'{i}-{Path(p).name}')
    _source_snapshot(OUT/'source.zip')
    with zipfile.ZipFile(OUT/'source.zip','a',zipfile.ZIP_DEFLATED) as archive:archive.write(__file__,'diagnostic/run.py')
    print(json.dumps(dict(event='predeclared',protocol_sha256=digest(OUT/'protocol.json'),episodes=16,decisions=40000)),flush=True)
    model=EquilibriumPPO.load(checkpoint,device='cpu');model.policy.set_training_mode(False)
    original_weights=_weights_hash(model);actor_hash=robust_swing.actor_weights_hash(model)
    assert actor_hash==selected['actor_weights_sha256']
    original_log_std=model.policy.log_std.detach().clone()
    initial_conditions={};episodes=[];began=time.monotonic()
    try:
        with preserved_rng():
            for std in STDS:
                label='mean' if std==0 else f'std{std:.2f}'
                with torch.no_grad():model.policy.log_std.copy_(original_log_std if std==0 else torch.full_like(original_log_std,math.log(std)))
                env=TrainingEnv(exp,POSES,randomization=None,reward_scale=1.)
                try:
                    for pose in POSES:
                        for start in STARTS:
                            torch.manual_seed(seed_for(pose,start))
                            obs,_=env.reset(options=dict(episode_seed=pose,start=start))
                            initial=dict(state=list(env.initial),observation={k:v.tolist() for k,v in obs.items()})
                            key=(pose,start)
                            if key not in initial_conditions:initial_conditions[key]=initial
                            else:assert initial_conditions[key]==initial
                            path=OUT/'traces'/f'{label}-{start}-{pose}.jsonl';trace=[];reward_sum=0.
                            with path.open('x') as stream:
                                while True:
                                    tensor,_=model.policy.obs_to_tensor(obs)
                                    with torch.no_grad():
                                        distribution=model.policy.get_distribution(tensor)
                                        mean=float(distribution.distribution.mean.item())
                                        realized_std=float(distribution.distribution.stddev.item())
                                        sampled=distribution.get_actions(deterministic=std==0).cpu().numpy().reshape(1)
                                    if std:assert math.isclose(realized_std,std,rel_tol=1e-6)
                                    action=np.clip(sampled,env.action_space.low,env.action_space.high)
                                    before=env.core.ground_truth.time_ns
                                    observed={k:v.tolist() for k,v in obs.items()}
                                    obs,reward,terminated,truncated,info=env.step(action)
                                    truth=env.core.ground_truth;reward_sum+=reward
                                    row=dict(step=env.steps,t_s=env.steps*.01,actor_observation=observed,distribution_mean_normalized=mean,distribution_std_normalized=realized_std,deterministic=std==0,sampled_unclipped_normalized=float(sampled[0]),action_normalized=float(action[0]),raw_action_m_s2=float(action[0])*env.action_scale,reward=float(reward),x=truth.x,v=truth.v,theta=truth.theta,omega=truth.omega,executed_acceleration_m_s2=env.core.diagnostics.executed_acceleration_m_s2,rail_braking=bool(env.core.diagnostics.rail_braking),physical_time_advanced=truth.time_ns>before)
                                    trace.append(row);stream.write(json.dumps(row,separators=(',',':'),allow_nan=False)+'\n')
                                    if terminated or truncated:break
                            result=env.result(hold_seconds=5.)
                            complete=result['steps']==2500 and result['fault_reason'] is None
                            balanced=[abs(r['x'])<.12 and abs(r['theta'])<.15 and abs(r['omega'])<1 for r in trace]
                            assert bool(result['hold_success'])==bool(complete and len(trace)>=500 and all(balanced[-500:]))
                            assert math.isclose(sum(balanced)/2500,result['balanced_fraction'],abs_tol=1e-12)
                            assert math.isclose(reward_sum/2500,result['score'],abs_tol=1e-10)
                            tail=trace[-500:];raw=np.asarray([r['raw_action_m_s2'] for r in trace])
                            result.update(condition=label,normalized_std=std,raw_std_m_s2=std*25,torch_rng_seed=seed_for(pose,start),complete=complete,full_balance=bool(complete and all(balanced)),total_benchmark_reward=reward_sum,equivalent_training_reward_scale_001=reward_sum*.01,tail_x_rms_m=float(np.sqrt(np.mean([r['x']**2 for r in tail]))) if complete else None,raw_action_delta_rms_m_s2=float(np.sqrt(np.mean(np.diff(raw)**2))),clipped_actions=sum(abs(r['sampled_unclipped_normalized'])>1 for r in trace),advanced_decisions=sum(r['physical_time_advanced'] for r in trace),trace_path=str(path.relative_to(OUT)),trace_sha256=digest(path),actor_weights_sha256=robust_swing.actor_weights_hash(model))
                            assert result['actor_weights_sha256']==actor_hash
                            episodes.append(result);_write_new(OUT/f'episode-{label}-{start}-{pose}.json',result)
                            print(json.dumps(dict(event='episode',condition=label,pose=pose,start=start,hold=result['hold_success'],balanced_fraction=result['balanced_fraction'],capture_s=result['first_one_second_capture_s'],longest_dwell_s=result['longest_balance_dwell_s'],score=result['score'])),flush=True)
                finally:env.close()
    finally:
        with torch.no_grad():model.policy.log_std.copy_(original_log_std)
    assert _weights_hash(model)==original_weights and sources()==identity and digest(checkpoint)==selected['sha256']
    assert digest(RUN/'recipe.json')==protocol['source_recipe_sha256'] and all(digest(p)==pin for p,pin in recipe['inputs'].items())
    summary=[]
    for std in STDS:
        for start in STARTS:
            rows=[r for r in episodes if r['normalized_std']==std and r['start']==start]
            captures=[r['first_one_second_capture_s'] for r in rows if r['first_one_second_capture_s'] is not None]
            summary.append(dict(normalized_std=std,raw_std_m_s2=std*25,start=start,episodes=len(rows),holds=sum(r['hold_success'] for r in rows),full_balances=sum(r['full_balance'] for r in rows),faults=sum(r['fault_reason'] is not None for r in rows),mean_balanced_fraction=float(np.mean([r['balanced_fraction'] for r in rows])),mean_longest_dwell_s=float(np.mean([r['longest_balance_dwell_s'] for r in rows])),captures=len(captures),mean_capture_s=float(np.mean(captures)) if captures else None,mean_score=float(np.mean([r['score'] for r in rows])),total_benchmark_reward=sum(r['total_benchmark_reward'] for r in rows),mean_tail_x_rms_m=float(np.mean([r['tail_x_rms_m'] for r in rows])) if all(r['tail_x_rms_m'] is not None for r in rows) else None,mean_raw_action_delta_rms_m_s2=float(np.mean([r['raw_action_delta_rms_m_s2'] for r in rows])),worst_max_abs_x_m=max(r['max_abs_x_m'] for r in rows)))
    result=dict(schema='cartpole-frozen-exploration-diagnostic-report-v1',completed=True,training_performed=False,hardware_accepted=False,deployable=False,protocol_sha256=digest(OUT/'protocol.json'),source_zip_sha256=digest(OUT/'source.zip'),checkpoint=selected,source=identity,actor_weights_sha256=actor_hash,log_std_restored=True,all_checkpoint_weights_restored=True,source_and_checkpoint_unchanged=True,wall_seconds=time.monotonic()-began,episodes=episodes,summary=summary,episode_count=len(episodes),proposed_decisions=sum(r['steps'] for r in episodes),advanced_decisions=sum(r['advanced_decisions'] for r in episodes),limitations=protocol['limitations'])
    assert result['episode_count']==16 and result['proposed_decisions']==40000
    _write_new(OUT/'report.json',result);_write_new(HERE/'report.json',result)
    print(json.dumps(dict(event='complete',summary=summary),indent=2),flush=True)
if __name__=='__main__':main()
