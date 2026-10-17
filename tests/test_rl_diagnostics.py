import json
from pathlib import Path
import numpy as np
import pytest
pytest.importorskip('stable_baselines3')
from test_ppo_training import make_experiment


def api():
    from cartpole_sdk.learning.diagnostics import DiagnosticEnv, run_pilot, summarize_suite
    return DiagnosticEnv, run_pilot, summarize_suite


def test_start_schedule_and_fixed_scaling_preserve_observed_input(tmp_path):
    Env, _, _ = api()
    exp = make_experiment(tmp_path)
    raw = Env(exp, (11,12), variant='upright')
    scaled = Env(exp, (11,12), variant='upright-scaled')
    mixed = Env(exp, (11,12), variant='mixed')
    try:
        starts=[]
        for _ in range(4):
            a,_=raw.reset(); b,_=scaled.reset(); mixed.reset()
            starts.append((raw.episode_seed,raw.start,mixed.episode_seed,mixed.start))
            np.testing.assert_allclose(b['state'],a['state']/scaled.state_scales)
            np.testing.assert_array_equal(b['valid'],a['valid'])
            np.testing.assert_allclose(b['age_s'],a['age_s']/.02)
            np.testing.assert_array_equal(raw._last_observation['state'],a['state'])
        assert starts==[(11,'upright',11,'hanging'),(12,'upright',11,'upright'),(11,'upright',12,'hanging'),(12,'upright',12,'upright')]
        # Explicit evaluation reset overrides training family for both starts.
        scaled.reset(options={'episode_seed':101,'start':'hanging'})
        assert scaled.start=='hanging'
        a,_=raw.reset(options={'episode_seed':99,'start':'upright'})
        b,_=scaled.reset(options={'episode_seed':99,'start':'upright'})
        a,ra,ta,xa,ia=raw.step(np.array([.1])); b,rb,tb,xb,ib=scaled.step(np.array([.1]))
        np.testing.assert_allclose(b['state'],a['state']/scaled.state_scales)
        assert (ra,ta,xa)==(rb,tb,xb)
    finally:
        raw.close(); scaled.close(); mixed.close()


def test_real_pilot_records_frozen_split_progress_and_non_deployable_checkpoint(tmp_path):
    _, run, summarize = api()
    exp=make_experiment(tmp_path)
    out=tmp_path/'pilot'
    kw=dict(variant='upright-scaled',seed=3,steps=16,every=8,training_seeds=(11,12),evaluation_seeds=(101,),n_steps=8,batch_size=4,epochs=1,evaluation_seconds=.05)
    report=run(exp,out,**kw)
    assert report['hardware_accepted'] is False and report['deployable'] is False
    assert [p['steps'] for p in report['evaluations']]==[0,8,16]
    assert all(len(p['episodes'])==2 for p in report['evaluations'])
    assert all(not ep['hold_success'] for p in report['evaluations'] for ep in p['episodes'])
    assert (out/'checkpoints/step-000000016.zip').exists()
    assert not (out/'actor.json').exists()
    assert report['provenance']['diagnostics_sha256']
    import zipfile
    with zipfile.ZipFile(out/'source.zip') as z:
        assert 'README.md' in z.namelist()
        assert 'src/cartpole_sdk/sim/model-provenance.json' in z.namelist()
    assert json.loads((out/'recipe.json').read_text())['training_seeds']==[11,12]
    assert (out/'training-episodes.jsonl').read_text()
    with pytest.raises(FileExistsError):run(exp,out,**kw)
    with pytest.raises(ValueError,match='overlap'):run(exp,tmp_path/'overlap',**dict(kw,evaluation_seeds=(11,)))
    assert not (tmp_path/'overlap').exists()
    summary=summarize([out])
    assert summary['variants']['upright-scaled']['optimizer_seeds']==[3]
    assert summary['convergence_proven'] is False
    with pytest.raises(ValueError,match='duplicate'):summarize([out,out])


def test_evaluation_preserves_global_rng_and_does_not_train(tmp_path):
    Env, _, _ = api()
    from cartpole_sdk.learning.diagnostics import evaluate_model
    from stable_baselines3 import PPO
    import random, torch
    exp=make_experiment(tmp_path)
    env=Env(exp,(11,),variant='upright')
    try:
        model=PPO('MultiInputPolicy',env,seed=3,n_steps=8,batch_size=4,n_epochs=1,device='cpu')
        weights={k:v.clone() for k,v in model.policy.state_dict().items()}
        py=random.getstate(); ns=np.random.get_state(); ts=torch.get_rng_state().clone()
        evaluate_model(model,exp,variant='upright',seeds=(101,),seconds=.05)
        assert random.getstate()==py
        now=np.random.get_state()
        assert now[0]==ns[0] and now[2:]==ns[2:]
        np.testing.assert_array_equal(now[1],ns[1])
        assert torch.equal(torch.get_rng_state(),ts)
        assert all(torch.equal(weights[k],v) for k,v in model.policy.state_dict().items())
        assert model.num_timesteps==0
    finally:env.close()


def test_summary_rejects_unequal_optimizer_recipes_and_source_corruption(tmp_path):
    _,run,summarize=api()
    exp=make_experiment(tmp_path)
    kw=dict(variant='upright',steps=8,every=8,training_seeds=(11,),evaluation_seeds=(101,),n_steps=8,batch_size=4,evaluation_seconds=.05)
    a,b=tmp_path/'a',tmp_path/'b'
    run(exp,a,seed=3,epochs=1,**kw)
    run(exp,b,seed=17,epochs=2,**kw)
    with pytest.raises(ValueError,match='incomparable'):summarize([a,b])
    with (a/'source.zip').open('ab') as f:f.write(b'tamper')
    with pytest.raises(ValueError,match='source'):summarize([a])


def test_summary_binds_report_identity_to_its_verified_recipe(tmp_path):
    _,run,summarize=api()
    exp=make_experiment(tmp_path)
    out=tmp_path/'probe'
    run(exp,out,variant='upright',seed=3,steps=8,every=8,training_seeds=(11,),evaluation_seeds=(101,),n_steps=8,batch_size=4,epochs=1,evaluation_seconds=.05)
    report=json.loads((out/'report.json').read_text())
    report['optimizer_seed']=123
    (out/'report.json').write_text(json.dumps(report))
    with pytest.raises(ValueError,match='recipe'):summarize([out])


def test_summary_checks_source_archive_hash(tmp_path):
    _,run,summarize=api()
    exp=make_experiment(tmp_path)
    out=tmp_path/'probe'
    run(exp,out,variant='upright',seed=3,steps=8,every=8,training_seeds=(11,),evaluation_seeds=(101,),n_steps=8,batch_size=4,epochs=1,evaluation_seconds=.05)
    with (out/'source.zip').open('ab') as f:f.write(b'tamper')
    with pytest.raises(ValueError,match='source'):summarize([out])
