import json
from pathlib import Path
import numpy as np
import pytest
pytest.importorskip('stable_baselines3')
from test_ppo_training import make_experiment


def api():
    import importlib.util
    assert importlib.util.find_spec('cartpole_sdk.learning.balance_experiment'), 'balance experiment harness missing'
    from cartpole_sdk.learning import balance_experiment
    return balance_experiment


def test_imitation_trains_actor_without_critic_std_or_rng_changes(tmp_path):
    m=api()
    import torch, random
    from stable_baselines3 import PPO
    from cartpole_sdk.learning.diagnostics import DiagnosticEnv
    env=DiagnosticEnv(make_experiment(tmp_path),(11,),variant='upright')
    model=PPO('MultiInputPolicy',env,seed=3,n_steps=8,batch_size=4,policy_kwargs=dict(net_arch=dict(pi=[64,64],vf=[64,64])))
    before={k:v.clone() for k,v in model.policy.state_dict().items()}
    ts=torch.get_rng_state().clone(); ns=np.random.get_state(); ps=random.getstate()
    try:
        fit=m.fit_teacher(model,dict(position_gain=8.,velocity_gain=6.,theta_gain=25.,omega_gain=3.),25.,updates=20,samples=128)
        assert fit['validation_raw_rmse_final']<fit['validation_raw_rmse_initial']
        assert all(torch.equal(v,before[k]) for k,v in model.policy.state_dict().items() if k=='log_std' or 'value' in k)
        assert any(not torch.equal(v,before[k]) for k,v in model.policy.state_dict().items() if 'policy_net' in k)
        assert torch.equal(ts,torch.get_rng_state()) and ps==random.getstate()
        np.testing.assert_array_equal(ns[1],np.random.get_state()[1])
    finally:env.close()


def test_short_matched_trial_and_evaluation_bind_saved_weights(tmp_path):
    m=api();exp=make_experiment(tmp_path);out=tmp_path/'trial'
    report=m.run_trial(exp,out,initialization='scratch',seed=3,steps=16,every=8,
        training_seeds=(11,12),evaluation_seeds=(101,),evaluation_seconds=.05,
        n_steps=8,batch_size=4,epochs=1)
    assert report['completed'] and not report['hardware_accepted']
    assert [e['steps'] for e in report['evaluations']]==[0,8,16]
    assert report['evaluations'][-1]['episodes'][0]['steps']==5
    assert 'tail_x_rms_m' in report['evaluations'][-1]['episodes'][0]
    assert not (out/'actor.json').exists()
    result=m.evaluate_saved(out,tmp_path/'fresh',seeds=(102,),seconds=.05)
    assert result['checkpoint_sha256']==report['evaluations'][-1]['checkpoint_sha256']
    with pytest.raises(ValueError,match='overlap'):m.evaluate_saved(out,tmp_path/'bad',seeds=(101,),seconds=.05)
    checkpoint=out/report['evaluations'][-1]['checkpoint']
    with checkpoint.open('ab') as stream:stream.write(b'corrupt')
    with pytest.raises(ValueError,match='hash'):m.evaluate_saved(out,tmp_path/'corrupt',seeds=(103,),seconds=.05)


def test_reject_overlap_and_budget_without_output(tmp_path):
    m=api();exp=make_experiment(tmp_path);out=tmp_path/'invalid'
    with pytest.raises(ValueError,match='overlap'):
        m.run_trial(exp,out,initialization='scratch',seed=3,training_seeds=(11,),evaluation_seeds=(11,))
    assert not out.exists()
    with pytest.raises(ValueError,match='budgets'):
        m.run_trial(exp,out,initialization='scratch',seed=3,steps=17,every=8,n_steps=8,batch_size=4)
    assert not out.exists()


def test_saved_evaluation_preserves_all_rng_and_policy_weights(tmp_path):
    m=api(); exp=make_experiment(tmp_path)
    import random, torch
    out=tmp_path/'trial'
    m.run_trial(exp,out,initialization='scratch',seed=3,steps=8,every=8,
        training_seeds=(11,),evaluation_seeds=(101,),evaluation_seconds=.05,n_steps=8,batch_size=4,epochs=1)
    random.seed(891);np.random.seed(892);torch.manual_seed(893)
    ps=random.getstate(); ns=np.random.get_state(); ts=torch.get_rng_state().clone()
    m.evaluate_saved(out,tmp_path/'fresh',seeds=(102,),seconds=.05)
    assert random.getstate()==ps
    np.testing.assert_array_equal(np.random.get_state()[1],ns[1])
    assert torch.equal(torch.get_rng_state(),ts)


def test_cli_accepts_flat_and_search_gains_artifacts(tmp_path):
    import importlib.util
    spec=importlib.util.spec_from_file_location('balance_cli',Path(__file__).parents[1]/'examples/balance_learning.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    assert hasattr(module,'read_gains_artifact'), 'gains artifact loader missing'
    flat=dict(position_gain=1.,velocity_gain=2.,theta_gain=40.,omega_gain=2.)
    file=tmp_path/'gains.json';file.write_text(json.dumps(flat))
    assert module.read_gains_artifact(file)==flat
    file.write_text(json.dumps(dict(schema='cartpole-observed-balance-teacher-v1',gains=flat)))
    assert module.read_gains_artifact(file)==flat
    file.write_text(json.dumps(dict(schema='unknown',gains=flat)))
    with pytest.raises(ValueError):module.read_gains_artifact(file)


def test_final_optimizer_metrics_are_flushed_after_last_update(tmp_path):
    import csv
    m=api();exp=make_experiment(tmp_path);out=tmp_path/'trial'
    m.run_trial(exp,out,initialization='scratch',seed=3,steps=16,every=8,
        training_seeds=(11,),evaluation_seeds=(101,),evaluation_seconds=.05,
        n_steps=8,batch_size=4,epochs=1,constraint='equilibrium')
    rows=list(csv.DictReader((out/'logs/progress.csv').open()))
    updates=[int(float(row['train/n_updates'])) for row in rows if row.get('train/n_updates')]
    assert updates[-1]==2
    assert rows[-1]['train/post_projection_approx_kl']!=''
