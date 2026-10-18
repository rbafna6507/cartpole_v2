import importlib.util
import numpy as np
import pytest
pytest.importorskip('stable_baselines3')
from test_ppo_training import make_experiment


def api():
    assert importlib.util.find_spec('cartpole_sdk.learning.swing_experiment'), 'swing experiment missing'
    from cartpole_sdk.learning import swing_experiment
    return swing_experiment


def test_curriculum_reset_repeats_and_preserves_reported_initial_state(tmp_path):
    m=api();exp=make_experiment(tmp_path)
    env=m.SwingEnv(exp,(31,32),reset_mode='curriculum')
    try:
        env.set_stage(1)
        a,_=env.reset(options=dict(episode_seed=31,start='capture'))
        initial=env.initial
        b,_=env.reset(options=dict(episode_seed=31,start='capture'))
        np.testing.assert_array_equal(a['state'],b['state'])
        assert initial==env.initial and env.result()['initial_state']==list(initial)
        assert abs(initial[2])<=2*np.pi/3 and env.start=='capture'
        with pytest.raises(ValueError):env.set_stage(3)
    finally:env.close()


def test_demonstrations_split_by_trajectory_and_reject_overlap(tmp_path):
    m=api()
    observations=dict(state=np.zeros((8,7)),valid=np.ones((8,7)),age_s=np.zeros((8,7)))
    observations['state'][:,3]=1
    file=tmp_path/'data.npz'
    np.savez(file,**observations,raw_action=np.arange(8.),episode=np.repeat([1,2,3,4],2))
    data=m.load_demonstrations(file,train_episodes=(1,2),validation_episodes=(3,4))
    assert data['train']['raw_action'].tolist()==[0,1,2,3]
    assert data['validation']['raw_action'].tolist()==[4,5,6,7]
    with pytest.raises(ValueError,match='overlap'):
        m.load_demonstrations(file,train_episodes=(1,2),validation_episodes=(2,3))


def test_observed_imitation_preserves_critic_std_rng_and_reduces_error(tmp_path):
    m=api()
    import torch,random
    from stable_baselines3 import PPO
    env=m.SwingEnv(make_experiment(tmp_path),(31,),reset_mode='mixed')
    model=PPO('MultiInputPolicy',env,seed=3,n_steps=8,batch_size=4,policy_kwargs=dict(net_arch=dict(pi=[64,64],vf=[64,64])))
    before={k:v.clone() for k,v in model.policy.state_dict().items()}
    rng=np.random.default_rng(5);state=rng.uniform(-.1,.1,(64,7));state[:,3]=1
    rows=dict(state=state,valid=np.ones((64,7)),age_s=np.zeros((64,7)),raw_action=state[:,2]*40)
    data=dict(train=rows,validation=rows)
    ts=torch.get_rng_state().clone();ps=random.getstate();ns=np.random.get_state()
    try:
        report=m.fit_demonstrations(model,data,25.,updates=30)
        assert report['final_rmse']<report['initial_rmse']
        assert all(torch.equal(v,before[k]) for k,v in model.policy.state_dict().items() if k=='log_std' or 'value' in k)
        assert torch.equal(ts,torch.get_rng_state()) and ps==random.getstate()
        np.testing.assert_array_equal(ns[1],np.random.get_state()[1])
    finally:env.close()


def test_episode_records_reset_stage_even_when_scheduler_advances(tmp_path):
    m=api();env=m.SwingEnv(make_experiment(tmp_path),(31,),reset_mode='curriculum')
    try:
        env.set_stage(0);env.reset(options=dict(episode_seed=31,start='capture'))
        env.set_stage(2);env.step([0.])
        assert env.result()['reset_curriculum_stage']==0
    finally:env.close()


def test_short_swing_trial_checkpoint_integrity_and_evaluation(tmp_path):
    m=api();out=tmp_path/'trial'
    report=m.run_trial(make_experiment(tmp_path),out,initialization='scratch',seed=3,steps=16,every=8,
        training_seeds=(31,32),evaluation_seeds=(301,),evaluation_seconds=.05,n_steps=8,batch_size=4,epochs=1)
    assert report['completed'] and [r['steps'] for r in report['evaluations']]==[0,8,16]
    assert set(report['evaluations'][-1]['by_start'])=={'hanging','upright'}
    m.evaluate_saved(out,tmp_path/'evaluation',seeds=(302,),seconds=.05)
    with pytest.raises(ValueError,match='overlap'):m.evaluate_saved(out,tmp_path/'bad',seeds=(301,),seconds=.05)
    cp=out/report['evaluations'][-1]['checkpoint'];cp.write_bytes(cp.read_bytes()+b'bad')
    with pytest.raises(ValueError,match='hash'):m.load_trial(out)


def test_demo_archive_matches_bytes_used_for_training_even_if_source_replaced(tmp_path,monkeypatch):
    m=api();file=tmp_path/'demonstrations.npz'
    state=np.zeros((8,7));state[:,3]=1
    arrays=dict(state=state,valid=np.ones((8,7)),age_s=np.zeros((8,7)),raw_action=np.zeros(8),episode=np.repeat([71,72],4))
    np.savez(file,**arrays);original=file.read_bytes()
    other=tmp_path/'other.npz';np.savez(other,**dict(arrays,raw_action=np.ones(8)))
    replacement=other.read_bytes();load=m.load_demonstrations
    def replacing_loader(*args,**kwargs):
        data=load(*args,**kwargs);file.write_bytes(replacement);return data
    monkeypatch.setattr(m,'load_demonstrations',replacing_loader)
    out=tmp_path/'run'
    m.run_trial(make_experiment(tmp_path),out,initialization='demonstrations',seed=3,steps=8,every=8,
        training_seeds=(31,),evaluation_seeds=(301,),evaluation_seconds=.05,n_steps=8,batch_size=4,epochs=1,
        demonstrations=file,train_episodes=(71,),validation_episodes=(72,),imitation_updates=1)
    assert (out/'demonstrations.npz').read_bytes()==original


def test_curriculum_boundary_updates_before_vector_auto_reset(tmp_path):
    m=api();exp=make_experiment(tmp_path);exp['simulation_config']['max_steps']=8
    out=tmp_path/'boundary'
    m.run_trial(exp,out,initialization='scratch',seed=3,steps=24,every=8,reset_mode='curriculum',
        training_seeds=(31,),evaluation_seeds=(301,),evaluation_seconds=.01,n_steps=8,batch_size=4,epochs=1)
    import json
    rows=[json.loads(line) for line in (out/'training-episodes.jsonl').read_text().splitlines()]
    assert [r['reset_curriculum_stage'] for r in rows]==[0,1,2]


def test_balance_anchor_restores_angle_feedback_despite_autocorrelated_demos(tmp_path):
    m=api()
    import torch
    from stable_baselines3 import PPO
    torch.set_num_threads(1)
    env=m.SwingEnv(make_experiment(tmp_path),(31,))
    model=PPO('MultiInputPolicy',env,seed=3,n_steps=8,batch_size=4,policy_kwargs=dict(net_arch=dict(pi=[64,64],vf=[64,64])))
    rng=np.random.default_rng(81);state=np.zeros((256,7));state[:,3]=1
    state[:,5]=rng.uniform(-2,2,256)
    rows=dict(state=state,valid=np.ones((256,7)),age_s=np.zeros((256,7)),raw_action=state[:,5])
    try:
        report=m.fit_demonstrations(model,dict(train=rows,validation=rows),25.,updates=300,balance_anchor_weight=10.)
        q=torch.tensor([[0.,0.,0.,1.,0.,0.,0.]],requires_grad=True)
        y=model.policy.get_distribution(dict(state=q,valid=torch.ones((1,7)),age_s=torch.zeros((1,7)))).distribution.mean*25
        y.backward()
        assert 30<float(q.grad[0,2])<50
        assert abs(float(q.grad[0,5]))<.5
        assert report['balance_anchor']['weight']==10.
        assert report['balance_anchor']['final_rmse']<report['balance_anchor']['initial_rmse']
    finally:env.close()
