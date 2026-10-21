#!/usr/bin/env python3
"""One teacher-initialized network, zero PPO; gated development/confirmation/export."""
import argparse
from dataclasses import asdict, replace
from hashlib import sha256
import json
import math
from pathlib import Path
import zipfile

import numpy as np
import torch

from cartpole_sdk.contracts import ValidationError
from cartpole_sdk.learning.balance_experiment import fit_teacher, source_identity
from cartpole_sdk.learning.candidate_parity import check_candidate, model_weights_sha256
from cartpole_sdk.learning.diagnostics import DiagnosticEnv, _source_snapshot
from cartpole_sdk.learning.model_experiment import validate_experiment
from cartpole_sdk.learning.projected_ppo import EquilibriumPPO, equilibrium_observation
from cartpole_sdk.learning.rollout import initial_state
from cartpole_sdk.policies.neural import load_neural_policy
from cartpole_sdk.policies.numeric_backend import NumpyActorBackend
from cartpole_sdk.policies.rig_observation import encode_rig_observation, rig_channels, select_rig_observation
from cartpole_sdk.sim.rig_gym_env import RigCartpoleEnv

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
TEACHER=HERE.parent/'teacher-centering-screen'
BASE=ROOT/'runs/policy-confidence-20261021/balance/teacher-seed47'
CANDIDATE=ROOT/'training/candidates/balance-20261021-centered'
BIASES=(0.,-.25,.25,-.5,.5)


def digest(path):return sha256(path.read_bytes()).hexdigest()


def write_new(path,value):
    with path.open('x') as stream:
        json.dump(value,stream,indent=2,sort_keys=True,allow_nan=False);stream.write('\n')


def declare():
    if (HERE/'protocol.json').exists() or CANDIDATE.exists():raise FileExistsError('new outputs required')
    teacher=json.loads((TEACHER/'final-report.json').read_text())
    frozen=json.loads((TEACHER/'frozen-winner.json').read_text())
    verification=json.loads((TEACHER/'verification.json').read_text())
    assert teacher['analytic_teacher_passed'] and teacher['summary']['holds']==20 and teacher['summary']['faults']==0
    assert teacher['frozen_winner_sha256']==digest(TEACHER/'frozen-winner.json')
    assert verification['final_report_sha256']==digest(TEACHER/'final-report.json')
    base=json.loads((BASE/'recipe.json').read_text())
    assert source_identity()==base['provenance']
    _source_snapshot(HERE/'source.zip')
    with zipfile.ZipFile(HERE/'source.zip','a',zipfile.ZIP_DEFLATED) as archive:
        archive.write(Path(__file__),'centered-initialization/run.py')
    protocol=dict(schema='cartpole-centered-teacher-initialized-network-v1',status='DEVELOPMENT_ONLY',
        simulation_only=True,hardware_accepted=False,deployable=False,
        label='Teacher-initialized network; no PPO training or improvement claim.',
        teacher=frozen['winner'],teacher_frozen_receipt_sha256=digest(TEACHER/'frozen-winner.json'),
        teacher_development_report_sha256=digest(TEACHER/'development-report.json'),
        teacher_confirmation_report_sha256=digest(TEACHER/'final-report.json'),teacher_verification_sha256=digest(TEACHER/'verification.json'),
        experiment=base['experiment'],original_profile_recipe_sha256=digest(BASE/'recipe.json'),
        source=source_identity(),source_zip_sha256=digest(HERE/'source.zip'),script_sha256=digest(Path(__file__)),
        initialization=dict(seed=47,architecture=[21,64,64,1],activation='tanh',policy_std=.02,actor_only=True,
            routine='Unchanged balance_experiment.fit_teacher followed once by EquilibriumPPO.project_equilibrium',
            updates=1500,samples=8192,validation_samples=4096,batch_size=512,
            synthetic_train_seed=51000,synthetic_validation_seed=51001,minibatch_seed=51002,
            internal_selection='Existing fit_teacher minimum synthetic validation RMSE at recorded updates; no rollout-based fit/tuning.',
            ppo_optimizer_updates=0,environment_training_steps=0),
        development=dict(seeds=[94000,94007],seconds=10.,encoder_bias_degrees=list(BIASES),episodes=10,
            teacher_comparison='Reuse unchanged saved analytic teacher closed-loop episodes on identical seeds/biases; also compare teacher/network outputs on each network-visited observed state.'),
        confirmation=dict(seeds=[97010,97011,97012,97013],seconds=30.,encoder_bias_degrees=list(BIASES),episodes=20),
        observation_law='Unchanged100Hz raw encoder profile; constant encoder_bias_rad before unchanged noise/quantization/rate observer.',
        hold_definition='Complete horizon without policy/simulator fault; entire final5s true abs(theta)<.15rad, abs(omega)<1rad/s, abs(x)<.12m.',
        gates=['All10 development final holds/no faults or stop without confirmation/export.',
               'Freeze checkpoint/hash before accessing97010..97013; all20 confirmation holds/no faults or stop without export.',
               'Actual candidate_parity.check_candidate, seeds94000/94007 at10s, strictSDK emission error<=1e-5; NumPy replay error<=1e-5.',
               'Create new final candidate only after all prior gates pass.'],
        export_candidate=str(CANDIDATE),workers=1,torch_threads=1,
        limitations=['One supervised seed/budget; not PPO improvement.','Development poses are already inspected; fresh confirmation only gates this frozen network.',
                    'Current free-swing-fitted friction model is unvalidated for tiny upright corrections; simulation gates do not qualify hardware.',
                    'No hardware, motor-enable change, runtime source edit, physical-model change, or neural fit variant search.'])
    write_new(HERE/'protocol.json',protocol)
    print(json.dumps(dict(protocol_sha256=digest(HERE/'protocol.json'),source_zip_sha256=protocol['source_zip_sha256'],teacher=protocol['teacher']),indent=2))


def evaluate(model,experiment,gains,seed,bias,seconds,stage):
    config,parameters,observations,_=validate_experiment(experiment)
    config=replace(config,max_steps=round(seconds*100));observations=replace(observations,encoder_bias_rad=math.radians(bias))
    env=RigCartpoleEnv(config,parameters=parameters,observation_config=observations,ttl_ms=experiment['ttl_ms'])
    path=HERE/stage/f'bias{bias:+.2f}-seed{seed}.jsonl';path.parent.mkdir(parents=True,exist_ok=True)
    try:
        encoded,_=env.reset(seed=seed,options=dict(state=initial_state(seed,'upright')))
        initial=asdict(env.ground_truth);reset_ns=env.ground_truth.time_ns
        states=[];raws=[];differences=[];dwell=longest=0.;max_x=abs(initial['x']);first_exit=None;fault=None
        with path.open('x') as stream:
            while not(env.terminated or env.truncated):
                try:select_rig_observation(env.sdk_observation,env.channels,contract=env.observation_contract)
                except ValidationError as error:fault=str(error);break
                obs=encode_rig_observation(env.sdk_observation,env.channels)
                assert all(np.array_equal(encoded[key],obs[key]) for key in obs)
                action,_=model.predict(encoded,deterministic=True)
                raw=float(action[0])*25.
                x,v,s,c,omega,_,_=obs['state']
                teacher=float(np.clip(gains['position_gain']*x+gains['velocity_gain']*v+gains['theta_gain']*math.atan2(s,c)+gains['omega_gain']*omega,-25.,25.))
                before=env.ground_truth.time_ns
                encoded,_,_,_,_=env.step([raw]);truth=env.ground_truth;state=asdict(truth)
                t=(truth.time_ns-reset_ns)/1e9
                balanced=abs(truth.theta)<.15 and abs(truth.omega)<1 and abs(truth.x)<.12
                dwell=dwell+(truth.time_ns-before)/1e9 if balanced else 0.;longest=max(longest,dwell)
                if not balanced and first_exit is None:first_exit=t
                max_x=max(max_x,abs(truth.x));states.append(state);raws.append(raw);differences.append(raw-teacher)
                stream.write(json.dumps(dict(t=t,observed=obs,truth=state,raw_command_m_s2=raw,
                    teacher_on_same_observation_m_s2=teacher,network_minus_teacher_m_s2=raw-teacher,
                    actual_executor_raw_m_s2=env.diagnostics.raw_acceleration_m_s2,
                    executed_acceleration_m_s2=env.diagnostics.executed_acceleration_m_s2,
                    balanced=balanced,fault_reason=env.fault_reason),sort_keys=True,allow_nan=False)+'\n')
        complete=fault is None and env.fault_reason is None and len(states)==config.max_steps
        tail=states[-500:] if complete else []
        rms=lambda v:float(np.sqrt(np.mean(np.square(v)))) if len(v) else None
        return dict(seed=seed,encoder_bias_degrees=bias,seconds=seconds,stage=stage,steps=len(states),initial_state=initial,
            final_state=asdict(env.ground_truth),full_horizon_complete=complete,hold_success=bool(complete and dwell>=5.-1e-9),
            final_balance_dwell_s=dwell,longest_balance_dwell_s=longest,first_exit_balance_s=first_exit,
            max_abs_x_m=max_x,final_window_x_rms_m=rms([s['x'] for s in tail]),
            final_window_x_mean_m=float(np.mean([s['x'] for s in tail])) if tail else None,
            final_window_centering_margin_m=.12-max(abs(s['x']) for s in tail) if tail else None,
            raw_command_delta_rms_m_s2=rms(np.diff(raws)),raw_command_rms_m_s2=rms(raws),
            teacher_disagreement_raw_rmse_m_s2=rms(differences),teacher_disagreement_max_abs_m_s2=max(map(abs,differences)) if differences else None,
            policy_fault_reason=fault,simulator_fault_reason=env.fault_reason,trace_path=str(path.relative_to(HERE)),trace_sha256=digest(path))
    finally:env.close()


def summary(rows):
    return dict(episodes=len(rows),holds=sum(row['hold_success'] for row in rows),
        faults=sum(row['policy_fault_reason'] is not None or row['simulator_fault_reason'] is not None for row in rows),
        worst_max_abs_x_m=max(row['max_abs_x_m'] for row in rows),
        worst_raw_command_delta_rms_m_s2=max(row['raw_command_delta_rms_m_s2'] for row in rows),
        worst_teacher_disagreement_raw_rmse_m_s2=max(row['teacher_disagreement_raw_rmse_m_s2'] for row in rows),
        by_bias=[dict(encoder_bias_degrees=b,holds=sum(row['hold_success'] for row in rows if row['encoder_bias_degrees']==b)) for b in BIASES])


def run():
    protocol=json.loads((HERE/'protocol.json').read_text())
    assert protocol['script_sha256']==digest(Path(__file__)) and protocol['source_zip_sha256']==digest(HERE/'source.zip')
    assert source_identity()==protocol['source']
    if (HERE/'fit-report.json').exists() or CANDIDATE.exists():raise FileExistsError('new run/candidate required')
    torch.set_num_threads(1)
    experiment=protocol['experiment'];gains=protocol['teacher']['gains']
    training_env=DiagnosticEnv(experiment,tuple(range(12000,12128)),variant='upright')
    try:
        model=EquilibriumPPO('MultiInputPolicy',training_env,seed=47,device='cpu',verbose=0,n_steps=1024,batch_size=64,
            n_epochs=10,gamma=.999,gae_lambda=.98,learning_rate=3e-6,
            policy_kwargs=dict(net_arch=dict(pi=[64,64],vf=[64,64]),activation_fn=torch.nn.Tanh,log_std_init=math.log(.02)))
        before={k:v.detach().clone() for k,v in model.policy.state_dict().items()}
        fit=fit_teacher(model,gains,25.,updates=1500,samples=8192)
        projection=model.project_equilibrium()
        assert model.num_timesteps==0
        assert all(torch.equal(value,before[name]) for name,value in model.policy.state_dict().items()
            if not name.startswith(('mlp_extractor.policy_net.','action_net.')))
        assert abs(float(model.predict(equilibrium_observation(),deterministic=True)[0][0]))<1e-7
        checkpoint=HERE/'teacher-initialized.zip';model.save(checkpoint)
        weights=model_weights_sha256(model)
        fit.update(label=protocol['label'],status='DEVELOPMENT_ONLY',hardware_accepted=False,deployable=False,
            protocol_sha256=digest(HERE/'protocol.json'),checkpoint_sha256=digest(checkpoint),model_weights_sha256=weights,
            equilibrium_projection_normalized=projection,equilibrium_projection_raw_m_s2=projection*25.,
            ppo_optimizer_updates=0,environment_training_steps=0,critic_std_unchanged=True)
        write_new(HERE/'fit-report.json',fit)
        print(json.dumps({k:fit[k] for k in ('validation_raw_rmse_initial','validation_raw_rmse_final','equilibrium_projection_raw_m_s2','checkpoint_sha256')}),flush=True)
        analytic=json.loads((TEACHER/'development-report.json').read_text())
        assert digest(TEACHER/'development-report.json')==protocol['teacher_development_report_sha256']
        teacher_rows={(row['seed'],row['encoder_bias_degrees']):row for row in analytic['episodes'] if row['candidate']==protocol['teacher']['name']}
        def phase(name):
            rows=[]
            settings=protocol[name]
            for bias in settings['encoder_bias_degrees']:
                for seed in settings['seeds']:
                    row=evaluate(model,experiment,gains,seed,bias,settings['seconds'],name)
                    if name=='development':
                        prior=teacher_rows[(seed,bias)]
                        row['matched_analytic_teacher']={k:prior[k] for k in ('hold_success','max_abs_x_m','final_window_x_rms_m','raw_command_delta_rms_m_s2','trace_sha256')}
                    rows.append(row)
                    print(json.dumps({k:row[k] for k in ('stage','seed','encoder_bias_degrees','hold_success','max_abs_x_m','teacher_disagreement_raw_rmse_m_s2')}),flush=True)
            assert model_weights_sha256(model)==weights and model.num_timesteps==0 and source_identity()==protocol['source']
            result=dict(status='DEVELOPMENT_ONLY',hardware_accepted=False,deployable=False,label=protocol['label'],
                completed=True,protocol_sha256=digest(HERE/'protocol.json'),checkpoint_sha256=digest(checkpoint),
                summary=summary(rows),episodes=rows)
            write_new(HERE/f'{name}-report.json',result)
            return result
        development=phase('development')
        def stop(reason):
            write_new(HERE/'final-report.json',dict(status='DEVELOPMENT_ONLY',hardware_accepted=False,deployable=False,
                completed=True,exported=False,reason=reason,label=protocol['label'],protocol_sha256=digest(HERE/'protocol.json'),
                checkpoint_sha256=digest(checkpoint),development_report_sha256=digest(HERE/'development-report.json')))
            print('STOP: '+reason,flush=True)
        if development['summary']['holds']!=10 or development['summary']['faults']:
            stop('Development10/10 final hold gate failed; no fresh confirmation or export.');return
        write_new(HERE/'frozen-network.json',dict(status='DEVELOPMENT_ONLY',hardware_accepted=False,deployable=False,
            checkpoint_sha256=digest(checkpoint),model_weights_sha256=weights,protocol_sha256=digest(HERE/'protocol.json'),
            development_report_sha256=digest(HERE/'development-report.json'),confirmation_not_yet_run=True))
        confirmation=phase('confirmation')
        if confirmation['summary']['holds']!=20 or confirmation['summary']['faults']:
            stop('Fresh confirmation20/20 final hold gate failed; no export.');return
        parity=check_candidate(model,experiment,HERE/'emission-parity',checkpoint_sha256=digest(checkpoint),seeds=(94000,94007),seconds=10.)
        if not parity['emission_parity_pass'] or parity['rejected_inputs']:
            stop('Emission parity gate failed; diagnostic artifact retained, final candidate not exported.');return
        actor_path=HERE/'emission-parity/actor.json'
        policy=load_neural_policy(actor_path,channels=rig_channels())
        numeric=NumpyActorBackend(policy.actor);maximum=0.;count=0
        for episode in parity['episodes']:
            for line in (HERE/'emission-parity'/episode['trace_path']).open():
                record=json.loads(line);obs=record['encoded_observation']
                maximum=max(maximum,abs(policy.predict_encoded(obs)-numeric.predict_encoded(obs)));count+=1
        if maximum>1e-5:
            stop('NumPy replay parity gate failed; final candidate not exported.');return
        assert source_identity()==protocol['source'] and model_weights_sha256(model)==weights and model.num_timesteps==0
        write_new(HERE/'numpy-parity.json',dict(status='DEVELOPMENT_ONLY',hardware_accepted=False,deployable=False,
            completed=True,parity_pass=True,observations=count,max_abs_raw_difference_m_s2=maximum,
            tolerance_m_s2=1e-5,actor_file_sha256=digest(actor_path),backend=numeric.provenance()))
        final=dict(status='DEVELOPMENT_ONLY',hardware_accepted=False,deployable=False,simulation_only=True,completed=True,
            exported=True,label=protocol['label'],ppo_optimizer_updates=0,environment_training_steps=0,
            protocol_sha256=digest(HERE/'protocol.json'),source_zip_sha256=digest(HERE/'source.zip'),
            fit_report_sha256=digest(HERE/'fit-report.json'),frozen_network_sha256=digest(HERE/'frozen-network.json'),
            development_report_sha256=digest(HERE/'development-report.json'),confirmation_report_sha256=digest(HERE/'confirmation-report.json'),
            checkpoint_path=str(checkpoint),checkpoint_sha256=digest(checkpoint),model_weights_sha256=weights,
            actor_file_sha256=digest(actor_path),actor_content_sha256=policy.actor['content_sha256'],
            actor_runtime_sha256=policy.actor['runtime_sha256'],emission_parity_report_sha256=digest(HERE/'emission-parity/report.json'),
            numpy_parity_report_sha256=digest(HERE/'numpy-parity.json'),candidate_path=str(CANDIDATE/'actor.json'),
            development_summary=development['summary'],confirmation_summary=confirmation['summary'],
            emission_max_abs_raw_difference_m_s2=parity['max_abs_raw_discrepancy_m_s2'],numpy_max_abs_raw_difference_m_s2=maximum,
            limitations=protocol['limitations'])
        write_new(HERE/'final-report.json',final)
        CANDIDATE.mkdir(parents=True,exist_ok=False)
        with (CANDIDATE/'actor.json').open('xb') as stream:stream.write(actor_path.read_bytes())
        load_neural_policy(CANDIDATE/'actor.json',channels=rig_channels())
        write_new(CANDIDATE/'receipt.json',dict(status='DEVELOPMENT_ONLY',hardware_accepted=False,deployable=False,label=protocol['label'],
            actor_file_sha256=digest(CANDIDATE/'actor.json'),actor_content_sha256=policy.actor['content_sha256'],
            checkpoint_sha256=digest(checkpoint),evidence_report_path=str(HERE/'final-report.json'),evidence_report_sha256=digest(HERE/'final-report.json')))
        print(json.dumps(final,indent=2),flush=True)
    finally:training_env.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=('declare','run'));args=parser.parse_args()
    declare() if args.mode=='declare' else run()
