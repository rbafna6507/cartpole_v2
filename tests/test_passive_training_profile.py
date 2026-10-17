"""A passive candidate can drive Gym without gaining unsupported acceptance."""
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path

import pytest

from cartpole_sdk.control.parameters import ControllerParameters
from cartpole_sdk.learning.model_experiment import digest, load_training_model
from cartpole_sdk.sim.config import SimulationConfig


def fixture(tmp_path):
    # Independent hand-computable coefficients: gravity=49.05, L=.2,
    # I=.75*.04*.2²=.0012, viscous torque rate=.00024, dry torque=.0018.
    freeze = dict(schema='cartpole-experimental-passive-freeze-v2', accepted=False,
        production_export_allowed=False,
        models=[dict(model='weak_coulomb', initializer='history_rawq:0.20',
                     coefficients=[49.05, .2, 0., 1.5])],
        parameters=dict(effective_length_m=.2, viscous_per_s=.2,
                        coulomb_rad_per_s2=1.5, local_angle_offset_rad=0.),
        source_identities=[dict(sha256='a'*64)], training=dict(episodes=6),
        training_quality=[dict(passed=False, all_release_poses_verified=False)])
    source = tmp_path/'freeze.json'
    source.write_text(json.dumps(freeze))
    config = asdict(SimulationConfig(control_steps=10, max_steps=50,
        pole_mass_kg=.04, rail_half_m=.3))
    config.update(hinge_coulomb_friction_nm=0., hinge_friction_velocity_scale_rad_s=.05)
    assumptions = dict(simulation_config=config, rationale='Explicit synthetic cart/mass assumptions.')
    parameters = asdict(ControllerParameters(rail=.3, bw=6., jmax=150.))
    observations = dict(angle_source='raw', encoder_counts=4096, angle_noise_std=0.,
        telemetry_delay_steps=0, command_delay_steps=0, dropout_probability=0.)
    return source, parameters, observations, assumptions


def build(tmp_path, mutate=None):
    from cartpole_sdk.learning.passive_profile import build_passive_training_bundle
    source, parameters, observations, assumptions = fixture(tmp_path)
    if mutate:
        mutate(source, parameters, observations, assumptions)
    result = build_passive_training_bundle(source, tmp_path/'profile',
        executor_parameters=parameters, observation_config=observations, assumptions=assumptions)
    return result, source


def test_candidate_converts_friction_and_preserves_unqualified_source(tmp_path):
    result, source = build(tmp_path)
    root = tmp_path/'profile'
    admitted = load_training_model(root/'model.json', development_only=True)
    config = admitted['simulation_config']
    assert config['effective_length_m'] == pytest.approx(.2)
    assert config['hinge_damping'] == pytest.approx(.00024)
    assert config['hinge_coulomb_friction_nm'] == pytest.approx(.0018)
    assert config['hinge_friction_velocity_scale_rad_s'] == .05
    assert admitted['model']['accepted_fit'] is False
    assert admitted['hardware_accepted'] is False
    provenance = json.loads((root/'provenance.json').read_text())
    assert provenance['freeze_sha256'] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert provenance['source_accepted'] is False
    assert provenance['training_quality'][0]['passed'] is False
    assert (root/'frozen-candidate.json').read_bytes() == source.read_bytes()
    assert result['hardware_accepted'] is False
    for name, expected in result['files_sha256'].items():
        assert hashlib.sha256((root/name).read_bytes()).hexdigest() == expected
    with pytest.raises(ValueError, match='development-only'):
        load_training_model(root/'model.json')


def test_profile_runs_real_governed_gym_with_same_acceleration_contract(tmp_path):
    build(tmp_path)
    from cartpole_sdk.learning.model_experiment import build_experiment
    from cartpole_sdk.sim.rig_gym_env import RigCartpoleEnv, RigObservationConfig
    root=tmp_path/'profile'
    read=lambda name: json.loads((root/name).read_text())
    exp=build_experiment(root/'model.json',executor_parameters=read('executor-parameters.json'),
        observation_config=read('observation-config.json'),prior_parameters=read('prior-parameters.json'),
        development_only=True)
    env=RigCartpoleEnv(SimulationConfig(**exp['simulation_config']),
        parameters=ControllerParameters(**exp['executor_parameters']),
        observation_config=RigObservationConfig(**exp['observation_config']))
    try:
        obs,_=env.reset(seed=1,options={'state':(0.,0.,math.pi+.5,0.)})
        assert obs['state'].shape == (7,)
        for _ in range(20):
            obs,reward,term,trunc,info=env.step([0.])
            assert not term and not trunc and math.isfinite(reward)
        assert abs(env.ground_truth.x)<1e-12
        assert env.ground_truth.time_ns == 200_000_000
        assert env.backend.plant.config.hinge_coulomb_friction_nm == pytest.approx(.0018)
    finally:
        env.close()


@pytest.mark.parametrize('change', ['coefficients','nonfinite','unknown_law','missing_config','rail','scale'])
def test_bad_candidate_or_implicit_inputs_leave_no_output(tmp_path,change):
    def mutate(source,p,o,a):
        f=json.loads(source.read_text())
        if change=='coefficients':f['models'][0]['coefficients'][0]=60.
        if change=='nonfinite':f['models'][0]['coefficients'][3]=float('nan')
        if change=='unknown_law':f['models'][0]['model']='static_friction'
        if change=='missing_config':a['simulation_config'].pop('cart_mass_kg')
        if change=='rail':p['rail']=.2
        if change=='scale':a['simulation_config']['hinge_friction_velocity_scale_rad_s']=.1
        source.write_text(json.dumps(f))
    with pytest.raises(ValueError):build(tmp_path,mutate)
    assert not (tmp_path/'profile').exists()


def test_existing_bundle_is_not_overwritten(tmp_path):
    build(tmp_path)
    before=(tmp_path/'profile/model.json').read_bytes()
    with pytest.raises(FileExistsError):build(tmp_path)
    assert (tmp_path/'profile/model.json').read_bytes()==before


def legacy_model(tmp_path):
    config=asdict(SimulationConfig(control_steps=10,max_steps=5))
    config.pop('hinge_coulomb_friction_nm',None)
    config.pop('hinge_friction_velocity_scale_rad_s',None)
    model=dict(schema='cartpole-development-model-v1',status='DEVELOPMENT_ONLY',
        simulation_config=config,rationale='Legacy explicit config.',limitations=['Unqualified model.'])
    model['content_sha256']=digest(model)
    path=tmp_path/'legacy.json';path.write_text(json.dumps(model));return path


def test_complete_legacy_model_keeps_zero_friction_and_original_content_hash(tmp_path):
    path=legacy_model(tmp_path);original=json.loads(path.read_text())
    loaded=load_training_model(path,development_only=True)
    assert loaded['simulation_config']['hinge_coulomb_friction_nm']==0.
    assert loaded['simulation_config']['hinge_friction_velocity_scale_rad_s']==.05
    assert loaded['model']['content_sha256']==original['content_sha256']
    assert json.loads(path.read_text())==original


@pytest.mark.parametrize('remove', ['cart_mass_kg', 'hinge_friction_velocity_scale_rad_s'])
def test_partial_config_is_not_implicitly_filled(tmp_path,remove):
    path=legacy_model(tmp_path);model=json.loads(path.read_text());model.pop('content_sha256')
    if remove=='cart_mass_kg':model['simulation_config'].pop(remove)
    else:model['simulation_config']['hinge_coulomb_friction_nm']=.001
    model['content_sha256']=digest(model);path.write_text(json.dumps(model))
    with pytest.raises(ValueError,match='explicit fields'):
        load_training_model(path,development_only=True)


def test_viscous_export_cannot_smuggle_an_unfitted_friction_term(tmp_path):
    from cartpole_sdk.identification.workflow import export_model
    config=asdict(SimulationConfig(control_steps=10));config.update(
        hinge_coulomb_friction_nm=.001,hinge_friction_velocity_scale_rad_s=.05)
    report=dict(accepted=True,kind='passive',model='viscous',parameters=dict(
        effective_length_m=.2,angular_damping_per_s=.2,coulomb_rad_per_s2=0.))
    with pytest.raises(ValueError,match='friction'):
        export_model(report,scope='passive-down',assumptions=dict(simulation_config=config,
            rationale='Synthetic test'),output=tmp_path/'bad.json')
    assert not (tmp_path/'bad.json').exists()


def test_preparation_cli_builds_a_loadable_profile_and_refuses_overwrite(tmp_path):
    import subprocess
    import sys
    source, parameters, observations, assumptions = fixture(tmp_path)
    for name,value in [('executor',parameters),('observations',observations),('assumptions',assumptions)]:
        (tmp_path/(name+'.json')).write_text(json.dumps(value))
    example=Path(__file__).resolve().parents[1]/'examples/prepare_passive_training.py'
    command=[sys.executable,str(example),'--freeze',str(source),'--executor-parameters',str(tmp_path/'executor.json'),
        '--observation-config',str(tmp_path/'observations.json'),'--assumptions',str(tmp_path/'assumptions.json'),
        '--output',str(tmp_path/'cli-profile')]
    result=subprocess.run(command,capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert load_training_model(tmp_path/'cli-profile/model.json',development_only=True)['hardware_accepted'] is False
    again=subprocess.run(command,capture_output=True,text=True)
    assert again.returncode==2
