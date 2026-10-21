from copy import deepcopy
from hashlib import sha256
import importlib.util
import json
import math
from pathlib import Path
import numpy as np
import pytest
pytest.importorskip('stable_baselines3')
from test_ppo_training import make_experiment


def api():
    assert importlib.util.find_spec('cartpole_sdk.learning.robust_swing'), 'robust full-task experiment missing'
    from cartpole_sdk.learning import robust_swing
    return robust_swing


@pytest.fixture
def warm(tmp_path):
    from cartpole_sdk.learning import swing_experiment as old
    from cartpole_sdk.learning.candidate_parity import check_candidate
    exp=make_experiment(tmp_path);run=tmp_path/'prior';parity=tmp_path/'parity'
    old.run_trial(exp,run,initialization='scratch',seed=7,steps=8,every=8,
        training_seeds=(31,),evaluation_seeds=(301,),evaluation_seconds=.02,n_steps=8,batch_size=4,epochs=1)
    model,recipe,selected=old.load_trial(run)
    check_candidate(model,exp,parity,checkpoint_sha256=selected['checkpoint_sha256'],seeds=(401,),seconds=.02)
    return exp,run,parity


def test_warm_binding_validates_archive_checkpoint_and_parity_before_loading(warm):
    m=api();exp,run,parity=warm
    result=m.load_warm_start(run,parity)
    assert result['binding']['optimizer_resume'] is False
    assert set((31,301,401))<=set(result['used_seeds'])
    assert result['binding']['checkpoint_sha256']==result['actor']['checkpoint_sha256']
    archive=run/'source.zip';archive.write_bytes(archive.read_bytes()+b'changed')
    with pytest.raises(ValueError,match='hash'):m.load_warm_start(run,parity)


def test_copy_preserves_critic_std_and_has_numeric_raw_parity(warm):
    m=api();exp,run,parity=warm
    import torch
    from cartpole_sdk.learning.projected_ppo import EquilibriumPPO
    env=m.RobustSwingEnv(exp,(51,),randomized=False,bias_degrees=0.,randomization_seed=9)
    model=EquilibriumPPO('MultiInputPolicy',env,seed=3,n_steps=8,batch_size=4,
        policy_kwargs=dict(net_arch=dict(pi=[64,64],vf=[64,64]),activation_fn=torch.nn.Tanh,log_std_init=math.log(.05)))
    before={k:v.clone() for k,v in model.policy.state_dict().items()}
    try:
        warm=m.load_warm_start(run,parity)
        m.copy_actor_weights(model,warm['actor'],action_scale=25.)
        assert all(torch.equal(v,before[k]) for k,v in model.policy.state_dict().items() if 'value' in k or k=='log_std')
        result=m.migration_parity(model,warm['actor'],exp)
        assert result['pass'] and result['compared_actions']>=30 and result['max_abs_raw_error_m_s2']<=1e-5
        bad=deepcopy(warm['actor']);bad['action_scale_m_s2']=10.
        with pytest.raises(ValueError,match='scale|contract|hash'):m.copy_actor_weights(model,bad,action_scale=25.)
    finally:env.close()


def test_mixed_reset_bias_and_randomization_are_reproducible_without_global_rng(tmp_path):
    m=api();exp=make_experiment(tmp_path)
    a=m.RobustSwingEnv(exp,(51,52),randomized=True,bias_degrees=1.,randomization_seed=9)
    b=m.RobustSwingEnv(exp,(51,52),randomized=True,bias_degrees=1.,randomization_seed=9)
    try:
        families=[];draws=[]
        for i in range(4):
            x,_=a.reset(seed=3 if i==0 else None);np.random.random(3)
            y,_=b.reset(seed=3 if i==0 else None)
            assert a.episode_parameters==b.episode_parameters
            np.testing.assert_array_equal(x['state'],y['state'])
            assert a.actor_angle_bias_rad==b.actor_angle_bias_rad
            families.append(a.start);draws.append(a.actor_angle_bias_rad)
            offset=a.actor_angle_bias_rad;a.step([0.]);assert a.actor_angle_bias_rad==offset
        assert families==['hanging','upright','hanging','upright'] and len(set(draws))==4
        assert max(map(abs,draws))<=math.pi/180
        assert a.episode_parameters['simulation_config']!=exp['simulation_config']
    finally:a.close();b.close()


def test_bias_only_changes_actor_input_not_truth_reward_or_sdk_timestamps(tmp_path):
    m=api();exp=make_experiment(tmp_path)
    a=m.RobustSwingEnv(exp,(51,),randomized=False,bias_degrees=0.,randomization_seed=9)
    b=m.RobustSwingEnv(exp,(51,),randomized=False,bias_degrees=1.,randomization_seed=9)
    try:
        x,_=a.reset(seed=3);y,_=b.reset(seed=3)
        assert not np.array_equal(x['state'][2:4],y['state'][2:4])
        for _ in range(3):
            _,ra,ta,ua,_=a.step([0.]);_,rb,tb,ub,_=b.step([0.])
            assert (ra,ta,ua)==(rb,tb,ub) and a.core.ground_truth==b.core.ground_truth
            assert a.core.sdk_observation==b.core.sdk_observation
    finally:a.close();b.close()


def test_fixed_fulltask_matrix_preserves_truth_metrics_and_rejects_seed_reuse(warm,tmp_path):
    m=api();exp,run,parity=warm
    out=tmp_path/'new'
    kwargs=dict(seed=3,randomized=True,bias_degrees=1.,steps=8,every=8,training_seeds=(51,),
        evaluation_seeds=(501,),heldout_seeds=(601,),evaluation_seconds=.02,n_steps=8,batch_size=4,epochs=1)
    with pytest.raises(ValueError,match='overlap'):
        m.run_trial(exp,out,warm_run=run,warm_parity=parity,**dict(kwargs,heldout_seeds=(301,)))
    assert not out.exists()
    report=m.run_trial(exp,out,warm_run=run,warm_parity=parity,**kwargs)
    assert report['completed'] and not report['hardware_accepted'] and not (out/'actor.json').exists()
    assert [e['steps'] for e in report['checkpoints']]==[0,8]
    assert report['initial_evaluation']['scenario_count']==7
    assert report['final_evaluation']['episode_count']==14 and report['heldout_evaluation']['episode_count']==14
    assert report['migration']['pass'] and report['warm_start']['optimizer_resume'] is False
    for filename in (report['initial_evaluation']['report'],report['final_evaluation']['report'],report['heldout_evaluation']['report']):
        result=json.loads((out/filename).read_text())
        assert set(e['start'] for e in result['episodes'])=={'hanging','upright'}
        assert all('true_theta_rms_rad' in e and 'true_x_rms_m' in e for e in result['episodes'])
    with pytest.raises(FileExistsError):m.run_trial(exp,out,warm_run=run,warm_parity=parity,**kwargs)


def test_non_raw_current_experiment_rejected_before_output(warm,tmp_path):
    m=api();exp,run,parity=warm
    exp=deepcopy(exp);exp['observation_config']['angle_source']='filtered'
    with pytest.raises(ValueError,match='raw'):
        m.RobustSwingEnv(exp,(51,),randomized=False,bias_degrees=0.,randomization_seed=9)
    with pytest.raises(ValueError,match='raw'):
        m.run_trial(exp,tmp_path/'invalid',warm_run=run,warm_parity=parity,
                    seed=3,randomized=False,bias_degrees=0.)
    assert not (tmp_path/'invalid').exists()


@pytest.mark.parametrize('change',('rate','features','scale','shape'))
def test_warm_actor_rejects_rehashed_incompatible_contract(warm,change):
    m=api();_,run,parity=warm
    actor=m.load_warm_start(run,parity)['actor']
    from cartpole_sdk.policies.neural import _digest
    bad=deepcopy(actor)
    if change=='rate':bad['rate_hz']=50
    if change=='features':bad['feature_order']=['state','age_s','valid']
    if change=='scale':bad['action_scale_m_s2']=10.
    if change=='shape':bad['layers'][0]['weights'][0].pop()
    bad.pop('content_sha256');bad['content_sha256']=_digest(bad)
    with pytest.raises(ValueError,match='scale|contract|shape'):
        m.copy_actor_weights(None,bad,action_scale=25.)
