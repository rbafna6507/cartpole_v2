#!/usr/bin/env python3
"""Independent frozen-checkpoint and saved trajectory verification; no new episodes."""
from hashlib import sha256
import json
import math
from pathlib import Path
import zipfile
import numpy as np
import torch
from cartpole_sdk.learning.balance_experiment import source_identity
from cartpole_sdk.learning.candidate_parity import model_weights_sha256
from cartpole_sdk.learning.projected_ppo import EquilibriumPPO
from cartpole_sdk.policies.neural import load_neural_policy
from cartpole_sdk.policies.rig_observation import rig_channels

HERE=Path(__file__).resolve().parent
digest=lambda path:sha256(path.read_bytes()).hexdigest()
protocol=json.loads((HERE/'protocol.json').read_text())
final=json.loads((HERE/'final-report.json').read_text())
fit=json.loads((HERE/'fit-report.json').read_text())
assert final['exported']
assert source_identity()==protocol['source']
assert digest(HERE/'source.zip')==protocol['source_zip_sha256']==final['source_zip_sha256']
assert digest(HERE/'run.py')==protocol['script_sha256']
with zipfile.ZipFile(HERE/'source.zip') as archive:
    assert archive.read('centered-initialization/run.py')==(HERE/'run.py').read_bytes()
for report in ('fit-report','frozen-network','development-report','confirmation-report'):
    assert digest(HERE/f'{report}.json')==final[report.replace('-','_')+'_sha256']
checkpoint=Path(final['checkpoint_path'])
assert digest(checkpoint)==final['checkpoint_sha256']==fit['checkpoint_sha256']
torch.set_num_threads(1)
model=EquilibriumPPO.load(checkpoint,device='cpu')
assert model.num_timesteps==0 and model._n_updates==0
assert model.policy.optimizer.state_dict()['state']=={}
assert model_weights_sha256(model)==final['model_weights_sha256']
policy=load_neural_policy(final['candidate_path'],channels=rig_channels())
assert policy.actor['content_sha256']==final['actor_content_sha256']
assert digest(Path(final['candidate_path']))==final['actor_file_sha256']
assert final['status']=='DEVELOPMENT_ONLY' and not final['deployable'] and not final['hardware_accepted']
gains=protocol['teacher']['gains'];maximum=0.;count=0;holds=0;worst_margin=1.;by_bias={}
for phase,expected_steps in [('development',1000),('confirmation',3000)]:
    report=json.loads((HERE/f'{phase}-report.json').read_text())
    assert report['summary']['faults']==0
    for episode in report['episodes']:
        path=HERE/episode['trace_path'];assert digest(path)==episode['trace_sha256']
        records=[json.loads(line) for line in path.open()]
        assert len(records)==expected_steps==episode['steps']
        assert all(record['fault_reason'] is None for record in records)
        for record in records:
            truth=record['truth']
            balanced=abs(truth['theta'])<.15 and abs(truth['omega'])<1 and abs(truth['x'])<.12
            assert record['balanced']==balanced
            x,v,s,c,w,_,_=record['observed']['state']
            teacher=float(np.clip(gains['position_gain']*x+gains['velocity_gain']*v+gains['theta_gain']*math.atan2(s,c)+gains['omega_gain']*w,-25,25))
            assert abs(teacher-record['teacher_on_same_observation_m_s2'])<1e-12
            assert record['raw_command_m_s2']==record['actual_executor_raw_m_s2']
        assert all(record['balanced'] for record in records[-500:]) and episode['hold_success']
        observations={key:np.asarray([record['observed'][key] for record in records],dtype=np.float32) for key in records[0]['observed']}
        prediction,_=model.predict(observations,deterministic=True)
        raw=np.asarray([record['raw_command_m_s2'] for record in records])
        error=float(np.max(np.abs(prediction[:,0].astype(float)*25.-raw)))
        maximum=max(maximum,error);count+=len(records);holds+=1
        if phase=='confirmation':
            margin=.12-max(abs(record['truth']['x']) for record in records[-500:]);worst_margin=min(worst_margin,margin)
            assert abs(margin-episode['final_window_centering_margin_m'])<1e-12
            key=str(episode['encoder_bias_degrees']);by_bias.setdefault(key,[]).append(episode['final_window_x_mean_m'])
assert maximum<=1e-5
verification=dict(status='DEVELOPMENT_ONLY',hardware_accepted=False,deployable=False,completed=True,
    episodes_rechecked=holds,commands_rechecked=count,raw_checkpoint_replay_max_abs_difference_m_s2=maximum,
    checkpoint_ppo_training_steps=model.num_timesteps,checkpoint_ppo_optimizer_updates=model._n_updates,
    ppo_optimizer_state_empty=True,source_identity_unchanged=True,trace_hashes_and_final_hold_gates_pass=True,
    teacher_commands_recomputed_on_all_observations=True,strict_sdk_candidate_load_pass=True,
    confirmation_worst_final_window_centering_margin_m=worst_margin,
    confirmation_final_window_x_means_by_bias_m=by_bias,
    final_report_sha256=digest(HERE/'final-report.json'),verification_script_sha256=digest(Path(__file__)))
with (HERE/'verification.json').open('x') as stream:
    json.dump(verification,stream,indent=2,sort_keys=True,allow_nan=False);stream.write('\n')
print(json.dumps(verification,indent=2))
