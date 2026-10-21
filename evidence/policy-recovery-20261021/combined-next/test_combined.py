from copy import deepcopy
import importlib.util
from pathlib import Path
import numpy as np
import pytest
import torch
from cartpole_sdk.learning.projected_ppo import EquilibriumPPO
from cartpole_sdk.learning.ppo import TrainingEnv
from cartpole_sdk.policies.neural import load_neural_policy
from cartpole_sdk.policies.rig_observation import rig_channels

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
spec=importlib.util.spec_from_file_location('combined_recovery',HERE/'run.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
@pytest.fixture
def inputs():
    import json
    exp=json.loads((HERE.parent/'teacher-transfer/protocol.json').read_text())['experiment']
    exp['simulation_config']['max_steps']=8
    actor=load_neural_policy(ROOT/'training/candidates/balance-recovery-20261021/actor.json',channels=rig_channels(angle_source='filtered')).actor
    return exp,actor

def test_filtered_transfer_preserves_mean_and_only_changes_actor(inputs):
    exp,actor=inputs;env=TrainingEnv(exp,[28400],reward_scale=.01)
    try:
        torch.set_num_threads(1)
        model=EquilibriumPPO('MultiInputPolicy',env,seed=11,n_steps=8,batch_size=4,n_epochs=1,
            policy_kwargs=dict(net_arch=dict(pi=[64,64],vf=[64,64]),activation_fn=torch.nn.Tanh))
        before={k:v.clone() for k,v in model.policy.state_dict().items()}
        m.copy_filtered_actor(model,actor,exp)
        policy=load_neural_policy(ROOT/'training/candidates/balance-recovery-20261021/actor.json',channels=rig_channels(angle_source='filtered'))
        for start in ('hanging','upright'):
            obs,_=env.reset(options=dict(episode_seed=28400,start=start))
            action,_=model.predict(obs,deterministic=True)
            assert abs(float(action[0])*25-policy.predict_encoded(obs))<1e-5
        for k,v in model.policy.state_dict().items():
            if not k.startswith(('mlp_extractor.policy_net.','action_net.')):assert torch.equal(v,before[k])
    finally:env.close()

def test_raw_experiment_is_rejected_before_copy(inputs):
    exp,actor=inputs;exp['observation_config']['angle_source']='raw'
    with pytest.raises(ValueError,match='filtered'):
        m.copy_filtered_actor(None,actor,exp)

def test_wrong_scale_is_rejected_before_copy(inputs):
    exp,actor=inputs;actor=deepcopy(actor);actor['action_scale_m_s2']=24
    with pytest.raises(ValueError):m.copy_filtered_actor(None,actor,exp)

@pytest.mark.parametrize('field', ['training_seeds','anchor_seeds','development_seeds','confirmation_seeds'])
def test_seed_partitions_reject_overlap(field):
    protocol=dict(training_seeds=list(range(28000,28004)),anchor_seeds=[28100],development_seeds=[98200,98201],confirmation_seeds=[98300,98301])
    other='development_seeds' if field!='development_seeds' else 'confirmation_seeds'
    protocol[field]=[protocol[other][0]]
    with pytest.raises(ValueError,match='overlap'):m.validate_seed_partitions(protocol)

def test_confirmation_and_development_are_not_anchor_inputs():
    protocol=dict(training_seeds=[28000],anchor_seeds=[28100],development_seeds=[98200],confirmation_seeds=[98300])
    assert m.validate_seed_partitions(protocol) is None

def test_reused_evaluator_accepts_filtered_scenarios(inputs,tmp_path):
    exp,actor=inputs;env=TrainingEnv(exp,[28400],reward_scale=.01)
    try:
        model=EquilibriumPPO('MultiInputPolicy',env,seed=11,n_steps=8,batch_size=4,n_epochs=1,
            policy_kwargs=dict(net_arch=dict(pi=[64,64],vf=[64,64]),activation_fn=torch.nn.Tanh))
        m.copy_filtered_actor(model,actor,exp)
        p=dict(experiment=exp,development_seeds=[28401],training_seeds=[28400],anchor_seeds=[28402],
            stress_scenarios=[dict(name='nominal',upstream_overrides={})])
        model.policy.set_training_mode(True)
        modes_before=[module.training for module in model.policy.modules()]
        result=m.evaluate(model,p,tmp_path/'evaluation',seconds=.02,checkpoint_sha256='a'*64,protocol_sha256='b'*64)
        assert [module.training for module in model.policy.modules()]==modes_before
        assert result['checkpoint_sha256']=='a'*64
        assert result['protocol_sha256']=='b'*64
        assert result['model_weights_sha256']==m.model_weights_sha256(model)
        assert len(result['episodes'])==2
        assert all(r['steps']==2 and r['expected']=='task_success' for r in result['episodes'])
    finally:env.close()
