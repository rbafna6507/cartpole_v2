from dataclasses import asdict
import json, math
import pytest
from cartpole_sdk.contracts import Observation, Sample, Session, UNITS
from cartpole_sdk.control.parameters import ControllerParameters
from examples.python_auto_portal import build_source, make_policy, replay_decisions


def obs(t=0):
    p=make_policy(asdict(ControllerParameters()),rate_hz=250)
    return Observation('test','clock',t//1000000,t,'test',tuple(
        Sample(c.entity,c.quantity,c.source,v,UNITS[c.quantity],c.frame_id,'test','valid',None,'estimated',t,t,t)
        for c,v in zip(p.channels+(p.raw_angle_channel,),(0.,0.,math.pi,0.,0.,0.,math.pi))))


def test_generated_matches_original():
    values=asdict(ControllerParameters(pw=3.,bw=10.,rail=.309))
    ns={};exec(compile(build_source(values,rate_hz=250,max_gap_periods=2),'policy.py','exec'),ns)
    generated=ns['create_policy']();reference=make_policy(values,rate_hz=250,max_gap_periods=2)
    assert asdict(generated.parameters)==values
    for p in (generated,reference):p.reset(Session('test','clock'))
    for i in range(35):
        assert generated.act(obs(i*4000000))==reference.act(obs(i*4000000))
        assert generated.mode==reference.mode
    assert generated.raw_angle_channel.source=='magnetic'
    assert generated.channels[2].source=='magnetic_filtered'


def test_incomplete_snapshot_rejected():
    values=asdict(ControllerParameters());del values['rail']
    with pytest.raises(ValueError,match='complete'):build_source(values,rate_hz=100)


def test_invalid_configuration_rejected():
    with pytest.raises(ValueError):build_source(asdict(ControllerParameters()),rate_hz=1000)
    with pytest.raises(ValueError):build_source(asdict(ControllerParameters(amax_s=26)),rate_hz=100)


def test_replay_calls_and_faults():
    records=[{'type':'session','session':json.loads(json.dumps(asdict(Session('test','clock'))))}]
    for o,a in zip((obs(0),obs(4000000),obs(20000000)),(1.,1.,None)):
        records.extend([{'type':'observation','observation':json.loads(json.dumps(asdict(o)))},
                        {'type':'policy_call','observation_sequence':o.sequence},
                        {'type':'action_request','observation_sequence':o.sequence,'acceleration_m_s2':a}])
    result=replay_decisions(records,asdict(ControllerParameters()),rate_hz=250)
    assert len(result)==3
    assert all(r['matches_recorded_action'] for r in result)
    assert result[0]['phase']=='swing'
    assert 'cadence' in result[-1]['fault_reason']
    assert result[-1]['theta']==pytest.approx(math.pi)


def test_missing_observation_fails():
    records=[{'type':'session','session':json.loads(json.dumps(asdict(Session('test','clock'))))},
             {'type':'policy_call','observation_sequence':4}]
    with pytest.raises(ValueError,match='missing observation'):replay_decisions(records,asdict(ControllerParameters()),rate_hz=250)


def test_uncalled_prearm_observation_does_not_change_first_action():
    records=[{'type':'session','session':json.loads(json.dumps(asdict(Session('test','clock'))))},
             {'type':'observation','observation':json.loads(json.dumps(asdict(obs(0))))},
             {'type':'observation','observation':json.loads(json.dumps(asdict(obs(100000000))))},
             {'type':'policy_call','observation_sequence':100},
             {'type':'action_request','observation_sequence':100,'acceleration_m_s2':0.}]
    rows=replay_decisions(records,asdict(ControllerParameters()),rate_hz=250)
    assert len(rows)==1 and rows[0]['requested_acceleration']==1.
    assert not rows[0]['matches_recorded_action']


def test_generated_policy_does_not_substitute_raw_for_missing_filtered_angle():
    from dataclasses import replace
    ns={};exec(build_source(asdict(ControllerParameters()),rate_hz=250),ns)
    policy=ns['create_policy']();policy.reset(Session('test','clock'))
    original=obs()
    missing=replace(original,samples=tuple(s for s in original.samples if s.source!='magnetic_filtered'))
    with pytest.raises(ValueError, match='host policy fault'):
        policy.act(missing)
    assert policy.fault_reason
