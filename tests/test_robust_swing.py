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


def fixed_randomization():
    return dict(schema='cartpole-training-randomization-v1', rationale='Fixed software test perturbations.',
        plant=dict(effective_length_scale=[1.02,1.02], angular_damping_scale=[1.,1.],
            coulomb_friction_scale=[1.,1.]),
        observation=dict(angle_noise_std=[0.,0.], telemetry_delay_steps=[0,0], command_delay_steps=[0,0]),
        encoder=dict(encoder_bias_rad=[.01,.01], encoder_sin_error_rad=[.02,.02], encoder_cos_error_rad=[.03,.03]))


def test_explicit_trial_randomization_is_recorded_and_used_for_episode_draws(warm,tmp_path):
    m=api();exp,run,parity=warm;settings=fixed_randomization();before=deepcopy(settings)
    output=tmp_path/'custom-randomization'
    report=m.run_trial(exp,output,warm_run=run,warm_parity=parity,seed=3,randomized=True,
        randomization=settings,bias_degrees=0.,steps=8,every=8,training_seeds=(51,),
        evaluation_seeds=(501,),heldout_seeds=(601,),evaluation_seconds=.02,n_steps=8,batch_size=4,epochs=1)
    recipe=json.loads((output/'recipe.json').read_text())
    assert settings==before and report['randomization']==recipe['randomization']==before
    episodes=[json.loads(line) for line in (output/'training-episodes.jsonl').read_text().splitlines()]
    assert episodes
    for episode in episodes:
        parameters=episode['episode_parameters']
        assert parameters['simulation_config']['effective_length_m']==pytest.approx(exp['simulation_config']['effective_length_m']*1.02)
        assert parameters['observation_config']['encoder_bias_rad']==.01
        assert parameters['observation_config']['encoder_sin_error_rad']==.02
        assert parameters['observation_config']['encoder_cos_error_rad']==.03
    assert all(episode['episode_parameters']['observation_config']['encoder_bias_rad']==0.
        for episode in json.loads((output/'final/report.json').read_text())['episodes'])


@pytest.mark.parametrize('randomized,settings',[(True,{}),(False,fixed_randomization())])
def test_trial_rejects_invalid_or_disabled_explicit_randomization_before_io(tmp_path,randomized,settings):
    m=api();exp=make_experiment(tmp_path);output=tmp_path/'invalid'
    with pytest.raises(ValueError,match='randomization|randomized'):
        m.run_trial(exp,output,warm_run=tmp_path/'missing-run',warm_parity=tmp_path/'missing-parity',
            seed=3,randomized=randomized,randomization=settings,bias_degrees=0.)
    assert not output.exists()


@pytest.mark.parametrize('has_recipe,randomized,override,expected_bw',[
    (True,True,None,6.),(True,True,10,10.),(True,False,None,6.),(False,True,None,6.)])
def test_cli_uses_profile_bandwidth_and_pins_selected_randomization(tmp_path,monkeypatch,has_recipe,randomized,override,expected_bw):
    m=api();exp=make_experiment(tmp_path)
    for filename,key in [('executor-parameters','executor_parameters'),('observation-config','observation_config'),('prior-parameters','prior_parameters')]:
        (tmp_path/f'{filename}.json').write_text(json.dumps(exp[key]))
    settings=fixed_randomization();path=tmp_path/'randomization.json'
    if has_recipe:path.write_text(json.dumps(settings))
    before={p.name:p.read_bytes() for p in tmp_path.glob('*.json')}
    calls=[]
    # Keep real profile admission and hashing; stop before the long default PPO budget.
    def capture(experiment,output,**kwargs):calls.append((experiment,kwargs))
    monkeypatch.setattr(m,'run_trial',capture)
    arguments=['--profile',str(tmp_path),'--output',str(tmp_path/'output'),
        '--warm-run',str(tmp_path/'prior'),'--warm-parity',str(tmp_path/'parity'),'--seed','3']
    if randomized:arguments.append('--randomized')
    if override is not None:arguments+=['--observer-bw',str(override)]
    assert m.main(arguments)==0
    assert len(calls)==1
    experiment,kwargs=calls[0]
    assert experiment['executor_parameters']['bw']==expected_bw
    assert kwargs['randomization']==(settings if has_recipe and randomized else None)
    assert kwargs['randomized'] is randomized
    if has_recipe:assert kwargs['input_files'][str(path)]==sha256(before[path.name]).hexdigest()
    assert before=={p.name:p.read_bytes() for p in tmp_path.glob('*.json')}


def rebind_actor_fixture(parity,actor):
    from cartpole_sdk.policies.neural import _digest
    actor.pop('content_sha256',None);actor['content_sha256']=_digest(actor)
    (parity/'actor.json').write_text(json.dumps(actor))
    for name in ('recipe.json','report.json'):
        path=parity/name;data=json.loads(path.read_text())
        data.update(actor_content_sha256=actor['content_sha256'],actor_runtime_sha256=actor['runtime_sha256'],
            actor_file_sha256=sha256((parity/'actor.json').read_bytes()).hexdigest())
        if name=='report.json':data['recipe_sha256']=sha256((parity/'recipe.json').read_bytes()).hexdigest()
        path.write_text(json.dumps(data))


def replace_archived_runtime_fixture(run,parity,*,rebind_actor):
    import zipfile
    name='rig/neural_runner.py';member='src/cartpole_sdk/'+name
    with zipfile.ZipFile(run/'source.zip') as archive:files={name:archive.read(name) for name in archive.namelist()}
    files[member]+=b'\n# Synthetic archived runner revision.\n'
    with zipfile.ZipFile(run/'source.zip','w') as archive:
        for path,data in files.items():archive.writestr(path,data)
    recipe=json.loads((run/'recipe.json').read_text())
    recipe['provenance']['code_sha256'][name]=sha256(files[member]).hexdigest()
    (run/'recipe.json').write_text(json.dumps(recipe))
    report=json.loads((run/'report.json').read_text());report.update(recipe)
    report['recipe_sha256']=sha256((run/'recipe.json').read_bytes()).hexdigest()
    report['source_zip_sha256']=sha256((run/'source.zip').read_bytes()).hexdigest()
    (run/'report.json').write_text(json.dumps(report))
    if rebind_actor:
        actor=json.loads((parity/'actor.json').read_text())
        actor['runtime_sha256'][name]=sha256(files[member]).hexdigest()
        rebind_actor_fixture(parity,actor)


def test_offline_migration_uses_verified_archived_runtime_and_records_current_difference(warm):
    m=api();_,run,parity=warm
    replace_archived_runtime_fixture(run,parity,rebind_actor=True)
    originals={path:path.read_bytes() for folder in (run,parity) for path in folder.rglob('*') if path.is_file()}
    result=m.load_warm_start(run,parity);binding=result['binding']
    assert binding['changed_runtime_files']==['rig/neural_runner.py']
    assert binding['original_actor_runtime_sha256']==result['actor']['runtime_sha256']
    root=Path(m.__file__).resolve().parents[1]
    assert binding['migration_runtime_sha256']['rig/neural_runner.py']==sha256((root/'rig/neural_runner.py').read_bytes()).hexdigest()
    assert all(path.read_bytes()==data for path,data in originals.items())
    from cartpole_sdk.policies.neural import load_neural_policy
    from cartpole_sdk.policies.rig_observation import rig_channels
    with pytest.raises(ValueError,match='source.*provenance'):
        load_neural_policy(parity/'actor.json',channels=rig_channels(angle_source='raw'))


def test_offline_migration_rejects_archived_runtime_hash_mismatch(warm):
    m=api();_,run,parity=warm
    replace_archived_runtime_fixture(run,parity,rebind_actor=True)
    replace_archived_runtime_fixture(run,parity,rebind_actor=False)
    with pytest.raises(ValueError,match='archived actor runtime hash mismatch'):m.load_warm_start(run,parity)


def test_offline_migration_rejects_rehashed_actor_that_differs_from_checkpoint(warm):
    m=api();_,run,parity=warm
    replace_archived_runtime_fixture(run,parity,rebind_actor=True)
    actor=json.loads((parity/'actor.json').read_text());actor['layers'][0]['weights'][0][0]+=.001
    rebind_actor_fixture(parity,actor)
    with pytest.raises(ValueError,match='differs from actual checkpoint weights'):m.load_warm_start(run,parity)


def test_offline_migration_requires_complete_runtime_pin_catalog(warm):
    m=api();_,run,parity=warm
    actor=json.loads((parity/'actor.json').read_text());actor['runtime_sha256'].pop('rig/neural_runner.py')
    rebind_actor_fixture(parity,actor)
    with pytest.raises(ValueError,match='inference provenance'):m.load_warm_start(run,parity)
