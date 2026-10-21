#!/usr/bin/env python3
"""Prepare new immutable inputs and observed-only balance anchors, no PPO fitting."""
from copy import deepcopy
from pathlib import Path
import importlib.util,json,math,shutil,zipfile
import numpy as np
import torch
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
spec=importlib.util.spec_from_file_location('combined_run',HERE/'run.py');run=importlib.util.module_from_spec(spec);spec.loader.exec_module(run)
from cartpole_sdk.learning.ppo import TrainingEnv
from cartpole_sdk.learning.projected_ppo import EquilibriumPPO
from cartpole_sdk.policies.neural import load_neural_policy
from cartpole_sdk.policies.numeric_backend import NumpyActorBackend
from cartpole_sdk.policies.rig_observation import rig_channels

def main():
    (HERE/'inputs').mkdir(exist_ok=False);(HERE/'profile').mkdir(exist_ok=False)
    prior=HERE.parent/'teacher-transfer';source=ROOT/'training/profiles/rl-encoder-20261021'
    for name in ('model.json','executor-parameters.json','prior-parameters.json'):shutil.copy2(source/name,HERE/'profile'/name)
    observation=json.loads((source/'observation-config.json').read_text());observation['angle_source']='filtered';run.write(HERE/'profile/observation-config.json',observation)
    shutil.copy2(ROOT/'training/candidates/balance-recovery-20261021/actor.json',HERE/'inputs/actor.json')
    shutil.copy2(prior/'bal-filtered-supervised-seed47.zip',HERE/'inputs/foundation.zip')
    shutil.copy2(prior/'protocol.json',HERE/'inputs/foundation-protocol.json')
    shutil.copy2(prior/'fit-report.json',HERE/'inputs/foundation-fit-report.json')
    experiment=deepcopy(json.loads((prior/'protocol.json').read_text())['experiment']);experiment['simulation_config']['max_steps']=2500
    specification=dict(schema='cartpole-filtered-combined-research-v1',status='DEVELOPMENT_ONLY',hardware_accepted=False,
        actor=str((HERE/'inputs/actor.json').relative_to(ROOT)),checkpoint=str((HERE/'inputs/foundation.zip').relative_to(ROOT)),
        anchors=str((HERE/'inputs/anchors.npz').relative_to(ROOT)),experiment=experiment,
        arms=['ppo','retained'],arm_definitions=dict(ppo='EquilibriumPPO: PPO plus zero-output equilibrium projection after each update',retained='EquilibriumPPO plus fixed-anchor actor-only supervised retention and a second equilibrium projection; not vanilla PPO'),optimizer_seeds=[11,23,47],training_seeds=list(range(28000,28128)),anchor_seeds=[28200,28201,28202,28203],
        development_seeds=[98400,98401,98402,98403],confirmation_seeds=list(range(98500,98508)),smoke_seeds=[98600,98601],
        hyperparameters=dict(n_steps=1024,batch_size=64,n_epochs=10,learning_rate=3e-6,policy_std=.05,gamma=.999,gae_lambda=.98,reward_scale=.01),
        retention=dict(updates=4,batch_size=256,learning_rate=1e-4,weight=1.,seed=98702),
        anchor_spec=dict(rows=8192,selection_seed=98701,episodes=[28200,28201,28202,28203],seconds=25.,
            source='Filtered observed channels from frozen candidate upright rollouts only; no ground truth, evaluation or old raw demonstrations in targets.',
            target='Frozen foundation Gaussian actor mean, normalized and unclipped.'),
        training_objective='Existing finite-horizon TrainingEnv dense reward + terminal dwell; 50% hanging and50% upright alternating; reward scale.01. No reward or physics changes.',
        training_randomization=None,development_seconds=25.,
        budgets=dict(pilot=dict(steps=102400,checkpoint_every=25600,evaluate_at=[0,51200,102400]),
                     long=dict(steps=1024000,checkpoint_every=51200,evaluate_at=[0,102400,256000,512000,1024000])),
        stress_scenarios=[dict(name='nominal',upstream_overrides={}),
            dict(name='encoder-bias-minus1',upstream_overrides=dict(encoder_bias_rad=-math.pi/180)),
            dict(name='encoder-bias-plus1',upstream_overrides=dict(encoder_bias_rad=math.pi/180)),
            dict(name='timing-5-3',upstream_overrides=dict(telemetry_delay_steps=5,command_delay_steps=3)),
            dict(name='bias-minus1-timing-5-3',upstream_overrides=dict(encoder_bias_rad=-math.pi/180,telemetry_delay_steps=5,command_delay_steps=3)),
            dict(name='bias-plus1-timing-5-3',upstream_overrides=dict(encoder_bias_rad=math.pi/180,telemetry_delay_steps=5,command_delay_steps=3))],
        selection='Development only; initial checkpoint is eligible. Require no upright hold/fault regression versus same-run initial actor; rank hanging final5s holds, then capture speed/dwell and centering. Freeze one choice before reserved60s confirmation; all failures retained.',
        long_run_recommendation='Run matched102400 pilot first. A passing software smoke alone does not establish swing-up acquisition or justify a larger cloud budget. Long budget is a separate fresh matched run from identical foundation, not an exact-resume claim.',
        confirmation='Use only after choosing and freezing a checkpoint; nominal and upstream bias/timing stress at60s, then actual numeric SDK rollouts and emission parity. Do not consume reserved starts in smoke, anchors, training or repeated selection.',
        limitations=['Supervised BAL foundation has hardware balance evidence; it has not learned joint swing-up. New PPO checkpoints inherit no hardware acceptance.',
            'RetainedPPO is an explicit post-PPO supervised retention intervention, not vanilla PPO or a trust-region guarantee.',
            'Four development poses repeatedly inspected can overfit; optimizer-seed repeats are paired on common starts.',
            'No existing raw demonstrations or raw-only robust transfer path are reused.',
            'Initial horizon and fault rewards depend on hidden time/dwell as before; no objective redesign is bundled.',
            'Plant,100Hz observer,bw10,jerk150,20ms leases and executor limits unchanged. Bias/timing scenarios are engineering stress points, not identified uncertainty.',
            'The unaltered fixed BAL actor fails the strict centered hold under±1degree model bias despite bounded pole motion; retain that baseline failure.',
            'Colab setup/CPU performance and long-run swing-up acquisition require actual execution; no cloud job launched by preparation.'])
    run.validate_seed_partitions(specification)
    run.write(HERE/'design.json',dict(intent='Reuse existing filtered-capable TrainingEnv, EquilibriumPPO, RetainedPPO and export/parity functions via a new evidence-only adapter.',
        authorized_scope='New evidence directory/new configs only; no production, simulator, cloud or hardware actions.',
        tasks=['Contract tests and exact actor-only transfer','Pin new profile/actor/checkpoint, disjoint seed partitions and training-only anchors','Real local PPO-only/retained smoke with save/load/export','Reuse existing Colab bundle/CLI with explicit evidence adapter job','Record readiness gaps and exact unexecuted launch commands']))
    # Anchor declaration is committed to disk before any anchor observations exist.
    run.write(HERE/'anchor-plan.json',dict(specification['anchor_spec'],actor_sha256=run.digest(HERE/'inputs/actor.json'),checkpoint_sha256=run.digest(HERE/'inputs/foundation.zip')))
    torch.set_num_threads(1)
    policy=load_neural_policy(HERE/'inputs/actor.json',channels=rig_channels(angle_source='filtered'));backend=NumpyActorBackend(policy.actor)
    model=EquilibriumPPO.load(HERE/'inputs/foundation.zip',device='cpu')
    if run.digest(HERE/'inputs/foundation.zip')!=policy.actor['checkpoint_sha256']:raise ValueError('foundation checkpoint mismatch')
    rows={k:[] for k in ('state','valid','age_s')};episodes=[];summaries=[]
    env=TrainingEnv(experiment,specification['anchor_seeds'],reward_scale=.01)
    try:
        for seed in specification['anchor_seeds']:
            observation,_=env.reset(options=dict(episode_seed=seed,start='upright'))
            while True:
                for k in rows:rows[k].append(observation[k].copy())
                episodes.append(seed)
                observation,_,terminated,truncated,_=env.step([backend.predict_encoded(observation)/25.])
                if terminated or truncated:break
            summaries.append(env.result())
    finally:env.close()
    rng=np.random.default_rng(98701);indices=rng.choice(len(episodes),8192,replace=False)
    observed={k:np.asarray(v,dtype=np.float32)[indices] for k,v in rows.items()}
    with torch.no_grad():
        tensor,_=model.policy.obs_to_tensor(observed);target=model.policy.get_distribution(tensor).distribution.mean.cpu().numpy()
    np.savez_compressed(HERE/'inputs/anchors.npz',**observed,target=target,episode=np.asarray(episodes)[indices],source_indices=indices)
    run.write(HERE/'anchor-receipt.json',dict(plan_sha256=run.digest(HERE/'anchor-plan.json'),rows_collected=len(episodes),rows_pinned=len(target),
        targets_use_ground_truth=False,validation_or_confirmation_used=False,episodes=summaries,sha256=run.digest(HERE/'inputs/anchors.npz')))
    paths=[p for parent in (ROOT/'src/cartpole_sdk',ROOT/'src/cartpole_vision') for p in parent.rglob('*') if p.is_file() and p.suffix in ('.py','.json')]
    paths += list((HERE/'inputs').iterdir())+list((HERE/'profile').iterdir())+[HERE/'run.py',HERE/'prepare.py',ROOT/'pyproject.toml',ROOT/'uv.lock']
    specification['bindings']={str(p.relative_to(ROOT)):run.digest(p) for p in sorted(paths)}
    run.write(HERE/'protocol.json',specification)
    with zipfile.ZipFile(HERE/'source.zip','x',zipfile.ZIP_DEFLATED) as archive:
        for p in sorted(paths):archive.write(p,p.relative_to(ROOT))
        archive.write(HERE/'protocol.json',(HERE/'protocol.json').relative_to(ROOT))
    print(json.dumps(dict(protocol_sha256=run.digest(HERE/'protocol.json'),anchors_sha256=run.digest(HERE/'inputs/anchors.npz'),anchor_holds=[s['hold_success'] for s in summaries],actor_content_sha256=policy.actor['content_sha256'])),flush=True)
if __name__=='__main__':main()
