"""Viewer uses the trained Gym dynamics and saved actor; rendering is a mirror."""
from dataclasses import asdict, replace
from importlib.util import find_spec
import json
from pathlib import Path
import sys
import subprocess

import pytest

pytestmark = pytest.mark.skipif(find_spec('mujoco') is None, reason='simulation extra required')
ROOT = Path(__file__).resolve().parents[1]
ACTOR = ROOT/'policies/working.json'
PROFILE = ROOT/'evidence/policy-recovery-20261021/combined-next/protocol.json'


def api():
    from cartpole_sdk.sim import policy_viewer
    return policy_viewer


def test_factory_exists_without_opening_a_window():
    assert find_spec('cartpole_sdk.sim.policy_viewer') is not None


def test_learned_session_matches_direct_gym_actions_and_state():
    from cartpole_sdk.sim.rig_gym_env import RigCartpoleEnv
    v = api()
    session = v.create_session(actor_path=ACTOR, experiment_path=PROFILE, seconds=.05, seed=98400)
    try:
        config, parameters, sensors, _ = v.validate_experiment(session.experiment)
        with_env = RigCartpoleEnv(replace(config, max_steps=5), parameters=parameters, observation_config=sensors)
        try:
            encoded, _ = with_env.reset(seed=98400, options={'state':session.initial_state})
            from cartpole_sdk.policies.numeric_backend import NumpyActorBackend
            numeric = NumpyActorBackend(session.policy.actor)
            for _ in range(5):
                action = numeric.predict_encoded(encoded)
                encoded, _, _, _, _ = with_env.step([action])
                session.advance(1)
                assert session.backend.ground_truth == with_env.ground_truth
            assert session.end_reason == 'horizon'
            assert session.decisions == 5
            before = session.backend.ground_truth
            assert session.advance(20)==0 and session.backend.ground_truth==before
        finally:
            with_env.close()
    finally:
        session.close()


def test_pause_reset_display_edits_and_seed_keep_authoritative_loop():
    import mujoco
    v=api();session=v.create_session(actor_path=ACTOR,experiment_path=PROFILE,seed=98400,seconds=.1)
    try:
        session.advance(3); expected=session.backend.ground_truth
        session.key_callback(32);session.apply_pending_commands();assert session.paused
        assert session.advance(4)==0 and session.backend.ground_truth==expected
        model=mujoco.MjModel.from_xml_string(session.backend.model_xml);data=mujoco.MjData(model)
        data.qpos[:]=[.5,1.];model.opt.timestep=.1
        v.copy_display_state(session,model,data)
        assert data.qpos.tolist()==session.backend.data.qpos.tolist()
        assert session.backend.ground_truth==expected and session.backend.model.opt.timestep==.001
        session.key_callback(ord('R'));session.apply_pending_commands()
        assert not session.paused and session.decisions==0
        session.advance(3);assert session.backend.ground_truth==expected
    finally:session.close()


@pytest.mark.parametrize('field', ['experiment_sha256','executor_parameters','observation_contract','action_scale_m_s2'])
def test_actor_profile_mismatch_refused_before_environment_creation(tmp_path, field):
    from cartpole_sdk.policies.neural import _digest
    v=api();actor=json.loads(ACTOR.read_text())
    if field=='experiment_sha256': actor[field]='0'*64
    elif field=='executor_parameters':actor[field]['bw']=6.
    elif field=='observation_contract':actor[field]['vision_max_age_ns']=100_000_000
    else:actor[field]=3.
    actor.pop('content_sha256');actor['content_sha256']=_digest(actor)
    path=tmp_path/'actor.json';path.write_text(json.dumps(actor))
    with pytest.raises(ValueError,match='experiment|snapshot|contract|scale'):
        v.create_session(actor_path=path,experiment_path=PROFILE)


def test_reference_uses_fitted_plant_and_saved_gains_at_one_khz():
    from cartpole_sdk import Channel
    from cartpole_sdk.control.policy import ReferencePolicy
    from cartpole_sdk.simulation import run_simulation
    from cartpole_sdk.sim.config import SimulationConfig
    v=api();session=v.create_session(controller='reference',experiment_path=PROFILE,start='upright',seconds=.02,seed=7)
    try:
        exp=json.loads(PROFILE.read_text())['experiment']
        assert session.backend.config.effective_length_m==exp['simulation_config']['effective_length_m']
        params=session.policy.controller.parameters
        assert asdict(params)==exp['executor_parameters']
        config=session.backend.config
        policy=ReferencePolicy(Channel('pole','angle','simulation','sim:upright+x'),
            Channel('cart','position','simulation','sim:upright+x'),start_mode='upright',parameters=params)
        result=run_simulation(policy,config=config,seed=7,state=session.initial_state)
        assert session.advance(20)==20
        assert session.backend.ground_truth==result.steps[-1].truth
        assert session.period_s==.001
    finally:session.close()


def test_missing_actor_runtime_binding_refused(tmp_path):
    from cartpole_sdk.policies.neural import _digest
    v=api();actor=json.loads(ACTOR.read_text());actor['runtime_sha256']['rig/client.py']='0'*64
    actor.pop('content_sha256');actor['content_sha256']=_digest(actor)
    path=tmp_path/'actor.json';path.write_text(json.dumps(actor))
    with pytest.raises(ValueError,match='provenance'):v.create_session(actor_path=path,experiment_path=PROFILE)


def test_headless_cli_and_help_work_without_torch_or_serial():
    v=api()
    result=subprocess.run([sys.executable,'-m','cartpole_sdk.sim.policy_viewer','--headless',
        '--seconds','.02','--actor',str(ACTOR),'--experiment',str(PROFILE)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    report=json.loads(result.stdout.splitlines()[-1])
    assert report['decisions']==2 and report['end_reason']=='horizon'
    assert report['hardware_accepted'] is False
