"""Offline diagnostics never acquire a rig or claim physical acceptance."""
import math
import pytest
from cartpole_sdk.control.feedback_diagnostics import replay_actions, simulate_feedback
from cartpole_sdk.control.parameters import ControllerParameters

P=ControllerParameters(pw=3.,bal_pw=4.5,pc1=-5.,pc2=-6.,bw=10.,catch_a=.25,approach_v=.2,rail=.309037507)

def trace():
    rows=[{'type':'host_controller','controller_parameters':P.__dict__,'rate_hz':250,'mode':'auto'}]
    for i in range(3):
        rows.extend([{'type':'state','state':dict(tick=4*i,unwrapped_tick=4*i,unwrapped_us=4000*i,
            x=0.,velocity=0.,angle_hat=math.pi,omega=0.,acceleration=0.,brake_direction=0.,theta=math.pi)},
            {'type':'action_request','request':dict(observation_sequence=4*i,acceleration_m_s2=1.)}])
    return rows

def test_replay_checks_real_actions_and_reports_first_disagreement():
    rows=trace()
    assert replay_actions(rows)==dict(actions=3,max_absolute_error=0.,mismatches=0,missing_states=0,first_mismatch=None)
    rows[-1]['request']['acceleration_m_s2']=.75
    result=replay_actions(rows)
    assert result['mismatches']==1
    assert result['max_absolute_error']==.25
    assert result['first_mismatch']['observation_sequence']==8

def test_replay_missing_state_is_visible_and_never_synthesized():
    rows=trace();del rows[-2]
    result=replay_actions(rows)
    assert result['actions']==2 and result['missing_states']==1

def test_replay_fails_on_missing_controller_snapshot():
    with pytest.raises(ValueError,match='controller snapshot'):
        replay_actions(trace()[1:])

@pytest.mark.parametrize('controller',['python','native_reference'])
def test_closed_loop_uses_governor_and_explicit_model_assumptions(controller):
    result=simulate_feedback(P,controller=controller,duration_s=.04,theta=math.pi)
    assert result['hardware_validated'] is False
    assert result['elapsed_s']==pytest.approx(.04)
    assert 0<result['final']['x']<.001
    assert 0<result['final']['velocity']<.05
    assert result['capture_time_s'] is None
    assert result['max_abs_acceleration']<=1.000001

def test_python_observer_reset_counterfactual_is_independent_of_gain_snapshot():
    common=dict(duration_s=.04,theta=math.pi-.1,observer_angle=math.pi-.2,observer_rate=.2)
    kept=simulate_feedback(P,reset_observer=False,**common)
    reset=simulate_feedback(P,reset_observer=True,**common)
    assert kept['initial_observer']!=reset['initial_observer']
    assert kept['parameters']==reset['parameters']
    assert reset['initial_observer']['rate']==0.
    assert reset['initial_observer']['angle']==reset['initial_raw_angle']

@pytest.mark.parametrize('kwargs',[{'duration_s':0.},{'duration_s':61.},{'rate_hz':1000},{'controller':'unknown'},{'theta':float('nan')},{'angular_damping_per_s':-1.}])
def test_invalid_experiment_rejected(kwargs):
    with pytest.raises(ValueError):simulate_feedback(P,**kwargs)


def test_replay_keeps_identical_ticks_in_different_sessions_separate():
    first=trace();second=trace()
    for records,session in ((first,'first'),(second,'second')):
        for row in records:
            if row['type']=='state':row['state']['sid']=session
            if row['type']=='action_request':row['request']['session_id']=session
    for row in second:
        if row['type']=='state':row['state']['x']=.1
        if row['type']=='action_request':row['request']['acceleration_m_s2']=-4.
    result=replay_actions(first+second)
    assert result['actions']==6 and result['mismatches']==0
