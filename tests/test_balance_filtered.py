"""Filtered learned feedback must retain independent raw-angle admission checks."""
from dataclasses import replace
import json
import math
import pytest
from cartpole_sdk.contracts import ValidationError
from cartpole_sdk.policies import neural
from cartpole_sdk.learning.balance_hardware import _load_policy
from test_balance_hardware import saved_actor, rehearsal, run
from test_neural_runner import DeadlineAwareShadowRig


def test_filtered_actor_loads_its_declared_source_and_executes_with_same_lease(tmp_path):
    path=saved_actor(tmp_path,mode='filtered',demand=.1)
    policy=_load_policy(path)
    assert policy.channels[2].source=='magnetic_filtered'
    with rehearsal() as rig:
        result=run(rig,path,execute=True)
        assert result['mode']=='execute'
        requests=[r['request'] for r in rig.records if r['type']=='action_request']
        assert requests and all(r['acceleration_m_s2']==.1 for r in requests)
        assert all(r['expires_at_ns']-r['issued_at_ns']==20_000_000 for r in requests)
        assert not rig.state.enabled


def test_filtered_actor_inference_uses_filtered_angle(tmp_path):
    path=saved_actor(tmp_path,mode='filtered')
    actor=json.loads(path.read_text())
    actor['layers'][0]['weights'][0][9]=1.  # age[7] then state sin-angle index2
    actor['layers'][1]['weights'][0][0]=1.
    actor['layers'][2]['weights'][0][0]=1.
    actor.pop('content_sha256');actor['content_sha256']=neural._digest(actor)
    path.write_text(json.dumps(actor))
    policy=_load_policy(path)
    with rehearsal(state=dict(theta=.01,angle_hat=.04)) as rig:
        policy.reset(rig.session)
        action=policy.act(rig.control_observation())
        assert action.acceleration_m_s2==pytest.approx(math.tanh(math.tanh(math.sin(.04))))


@pytest.mark.parametrize('guard_profile',['commissioning','rig'])
def test_filtered_start_does_not_hide_large_raw_angle(tmp_path,guard_profile):
    path=saved_actor(tmp_path,mode='filtered')
    with rehearsal(state=dict(theta=.08,angle_hat=.01)) as rig:
        with pytest.raises(ValidationError,match='balance-only'):
            run(rig,path,execute=True,guard_profile=guard_profile)
        assert not any(c[1]=='ARM' for c in rig.commands)


def test_filtered_commissioning_run_still_checks_raw_angle(tmp_path):
    class RawDeparts(DeadlineAwareShadowRig):
        def wait_state(self,**kwargs):
            super().wait_state(**kwargs)
            self._state=replace(self._state,theta=.16,angle_hat=.02)
            self._history[self._state.unwrapped_tick]=self._state
            return self._state
    path=saved_actor(tmp_path,mode='filtered')
    with rehearsal(rig_type=RawDeparts) as rig:
        with pytest.raises(ValidationError,match='balance-only'):
            run(rig,path,execute=True)
        assert len([r for r in rig.records if r['type']=='action_request'])==1
        assert not rig.state.enabled


@pytest.mark.parametrize('problem',['missing','stale','skew'])
def test_filtered_guard_requires_fresh_synchronous_raw_sample(tmp_path,problem):
    path=saved_actor(tmp_path,mode='filtered')
    policy=_load_policy(path)
    with rehearsal() as rig:
        policy.reset(rig.session)
        obs=rig.control_observation()
        obs=replace(obs,available_ns=obs.available_ns+100_000_000,samples=tuple(
            replace(s,acquired_ns=s.acquired_ns+100_000_000,effective_ns=s.effective_ns+100_000_000,
                    received_ns=s.received_ns+100_000_000) for s in obs.samples))
        samples=[]
        for s in obs.samples:
            if s.source=='magnetic' and s.quantity=='angle':
                if problem=='missing':continue
                s=replace(s,effective_ns=obs.available_ns-(21_000_000 if problem=='stale' else 11_000_000))
            samples.append(s)
        with pytest.raises(ValidationError):
            policy.validate_start(replace(obs,samples=tuple(samples)))


def test_filtered_loader_still_checks_runtime_provenance(tmp_path):
    path=saved_actor(tmp_path,mode='filtered',bad_runtime=True)
    with pytest.raises(ValidationError,match='provenance'):
        _load_policy(path)


def test_filtered_guard_checks_combined_raw_and_all_selected_skew(tmp_path):
    path=saved_actor(tmp_path,mode='filtered')
    policy=_load_policy(path)
    with rehearsal() as rig:
        policy.reset(rig.session)
        original=rig.control_observation()
        now=original.available_ns+100_000_000
        samples=[]
        for s in original.samples:
            lag=(20_000_000 if s.source=='magnetic' and s.quantity=='angle' else
                 10_000_000 if s.source=='magnetic_filtered' else 0)
            samples.append(replace(s,acquired_ns=now,effective_ns=now-lag,received_ns=now))
        with pytest.raises(ValidationError,match='skew'):
            policy.validate_start(replace(original,available_ns=now,samples=tuple(samples)))
