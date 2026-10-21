import importlib.util
import json
import math
from pathlib import Path
import random

import numpy as np
import pytest
pytest.importorskip('stable_baselines3')
from test_ppo_training import make_experiment


def api():
    assert importlib.util.find_spec('cartpole_sdk.learning.error_training'), 'angle-error experiment is missing'
    from cartpole_sdk.learning import error_training
    return error_training


def test_rotation_changes_only_valid_angle_features_without_aliasing():
    m=api()
    obs=dict(state=np.array([.01,.02,0.,1.,.3,.4,0.]),valid=np.ones(7),age_s=np.arange(7)/1000)
    rotated=m.bias_observation(obs,math.pi/180)
    assert math.atan2(rotated['state'][2],rotated['state'][3])==pytest.approx(math.pi/180)
    np.testing.assert_array_equal(rotated['state'][[0,1,4,5,6]],obs['state'][[0,1,4,5,6]])
    for key in ('valid','age_s'):np.testing.assert_array_equal(rotated[key],obs[key])
    assert obs['state'][2]==0
    rotated['state'][0]=99
    assert obs['state'][0]==.01
    obs['valid'][2]=0
    np.testing.assert_array_equal(m.bias_observation(obs,.03)['state'],obs['state'])


@pytest.mark.parametrize('amplitude',[-.01,3.01,float('nan'),float('inf'),True])
def test_rejects_out_of_scope_bias_amplitudes(tmp_path,amplitude):
    m=api()
    with pytest.raises(ValueError,match='bias'):
        m.AngleErrorEnv(make_experiment(tmp_path),(11,),bias_degrees=amplitude,bias_seed=7)


def test_bias_is_episode_constant_and_does_not_change_reward_truth_or_sensor_history(tmp_path):
    m=api();exp=make_experiment(tmp_path)
    from cartpole_sdk.learning.diagnostics import DiagnosticEnv
    base=DiagnosticEnv(exp,(11,),variant='upright')
    env=m.AngleErrorEnv(exp,(11,),bias_degrees=1.,bias_seed=7,fixed_bias_degrees=1.)
    try:
        a,_=base.reset(seed=3);b,info=env.reset(seed=3)
        assert info['actor_angle_bias_rad']==pytest.approx(math.pi/180)
        for _ in range(4):
            assert math.atan2(b['state'][2],b['state'][3])-math.atan2(a['state'][2],a['state'][3])==pytest.approx(math.pi/180)
            for key in ('valid','age_s'):np.testing.assert_array_equal(a[key],b[key])
            np.testing.assert_array_equal(a['state'][[0,1,4,5,6]],b['state'][[0,1,4,5,6]])
            a,ra,ta,ua,_=base.step([0.]);b,rb,tb,ub,_=env.step([0.])
            assert (ra,ta,ua)==(rb,tb,ub)
            assert base.core.ground_truth==env.core.ground_truth
    finally:base.close();env.close()


def test_bias_rng_reproducible_independent_of_evaluation_and_global_rng(tmp_path):
    m=api();exp=make_experiment(tmp_path)
    a=m.AngleErrorEnv(exp,(11,),bias_degrees=3.,bias_seed=99)
    b=m.AngleErrorEnv(exp,(11,),bias_degrees=3.,bias_seed=99)
    try:
        py=random.getstate();ns=np.random.get_state()
        first=[];second=[]
        for i in range(5):
            a.reset(seed=3 if i==0 else None);first.append(a.actor_angle_bias_rad)
            np.random.random(10);random.random()
            b.reset(seed=3 if i==0 else None);second.append(b.actor_angle_bias_rad)
        assert first==second and len(set(first))==5 and max(map(abs,first))<=math.pi/60
        a.reset(seed=3);assert a.actor_angle_bias_rad==first[0]
        random.setstate(py);np.random.set_state(ns)
    finally:a.close();b.close()


@pytest.mark.parametrize('bw',[6,8,10])
def test_profile_bw_override_rebuilds_without_rewriting_inputs(tmp_path,bw):
    m=api();exp=make_experiment(tmp_path)
    for filename,key in [('executor-parameters','executor_parameters'),('observation-config','observation_config'),('prior-parameters','prior_parameters')]:
        (tmp_path/f'{filename}.json').write_text(json.dumps(exp[key]))
    before={p.name:p.read_bytes() for p in tmp_path.glob('*.json')}
    rebuilt,pins=m.load_profile(tmp_path,observer_bw=bw,seconds=.05)
    assert rebuilt['executor_parameters']['bw']==bw
    assert rebuilt['simulation_config']==exp['simulation_config']
    assert rebuilt['admission']==exp['admission']
    assert before=={p.name:p.read_bytes() for p in tmp_path.glob('*.json')}
    assert len(pins)==4
    with pytest.raises(ValueError,match='observer'):m.load_profile(tmp_path,observer_bw=7)


class ZeroPolicy:
    def predict(self,observation,deterministic=True):return np.array([0.]),None


def test_evaluation_reports_true_errors_separately_and_preserves_rng(tmp_path):
    m=api();exp=make_experiment(tmp_path)
    import torch
    py=random.getstate();ns=np.random.get_state();ts=torch.get_rng_state().clone()
    r=m.evaluate_errors(ZeroPolicy(),exp,seeds=(101,),seconds=.05)
    assert [e['bias_degrees'] for e in r['episodes']]==[0.,-.5,.5,-1.,1.]
    assert len({e['true_theta_rms_rad'] for e in r['episodes']})==1
    for episode in r['episodes']:
        assert episode['true_theta_rms_rad']==pytest.approx(math.sqrt(sum(t['theta']**2 for t in episode['trajectory'])/5))
    assert random.getstate()==py and torch.equal(torch.get_rng_state(),ts)
    np.testing.assert_array_equal(np.random.get_state()[1],ns[1])


def test_tiny_trial_checkpoint_replay_provenance_and_refusals(tmp_path):
    m=api();exp=make_experiment(tmp_path);out=tmp_path/'trial'
    kwargs=dict(seed=3,bias_degrees=1.,steps=8,every=8,training_seeds=(11,),evaluation_seeds=(101,),
        evaluation_seconds=.05,n_steps=8,batch_size=4,epochs=1,imitation_updates=1)
    with pytest.raises(ValueError,match='overlap'):
        m.run_trial(exp,tmp_path/'invalid',**dict(kwargs,evaluation_seeds=(11,)))
    assert not (tmp_path/'invalid').exists()
    report=m.run_trial(exp,out,**kwargs)
    assert report['completed'] and report['hardware_accepted'] is False and report['deployable'] is False
    assert [e['steps'] for e in report['evaluations']]==[0,8]
    assert len(report['evaluations'][-1]['episodes'])==5 and not (out/'actor.json').exists()
    assert report['teacher_gains']==dict(position_gain=1.,velocity_gain=2.,theta_gain=40.,omega_gain=2.)
    fresh=m.evaluate_saved(out,tmp_path/'fresh',seeds=(102,),seconds=.05)
    assert fresh['checkpoint_sha256']==report['evaluations'][-1]['checkpoint_sha256']
    with pytest.raises(FileExistsError):m.run_trial(exp,out,**kwargs)
    with pytest.raises(ValueError,match='overlap'):m.evaluate_saved(out,tmp_path/'bad',seeds=(101,),seconds=.05)
    cp=out/report['evaluations'][-1]['checkpoint'];cp.write_bytes(cp.read_bytes()+b'changed')
    with pytest.raises(ValueError,match='hash'):m.evaluate_saved(out,tmp_path/'changed',seeds=(103,),seconds=.05)


@pytest.mark.parametrize('degrees',[-3.,3.])
def test_exact_bias_scope_boundary_is_supported(degrees):
    m=api();obs=dict(state=np.array([0.,0.,0.,1.,0.,0.,0.]),valid=np.ones(7),age_s=np.zeros(7))
    rotated=m.bias_observation(obs,math.radians(degrees))
    assert math.atan2(rotated['state'][2],rotated['state'][3])==pytest.approx(math.radians(degrees))


def test_invalid_budget_and_profile_pins_refuse_before_creating_output(tmp_path):
    m=api();exp=make_experiment(tmp_path)
    with pytest.raises(ValueError,match='budgets'):
        m.run_trial(exp,tmp_path/'bad',seed=3,bias_degrees=1.,steps=7,every=8,n_steps=8,batch_size=4)
    with pytest.raises(ValueError,match='hash'):
        m.run_trial(exp,tmp_path/'bad',seed=3,bias_degrees=1.,input_files={str(tmp_path/'model.json'):'0'*64})
    assert not (tmp_path/'bad').exists()


def test_cli_help_and_validation_do_not_train(tmp_path,capsys):
    m=api()
    with pytest.raises(SystemExit) as help_exit:m.main(['--help'])
    assert help_exit.value.code==0 and 'actor-input angle' in capsys.readouterr().out
    with pytest.raises(SystemExit) as invalid:m.main(['train','--profile',str(tmp_path),'--output',str(tmp_path/'bad'),
                                                    '--seed','3','--bias-degrees','1','--observer-bw','7'])
    assert invalid.value.code==2 and not (tmp_path/'bad').exists()
