"""Duration variation must stay within the same bounded hardware experiment."""
import math
from unittest.mock import patch
import pytest
from cartpole_sdk.contracts import ValidationError
from cartpole_sdk.identification import experiments as p
from test_system_id_experiments import observation, scripted_rig

@pytest.mark.parametrize("duration",(.45,.65,.8,1.))
def test_duration_changes_frequency_with_zero_endpoints(duration):
    assert p.waveform(0,.01,pulse_seconds=duration)==(0.,)*4
    assert p.waveform(duration,.01,pulse_seconds=duration)==(0.,)*4
    for fraction in (.13,.37,.61,.83):
        t=duration*fraction;h=1e-6
        a=p.waveform(t-h,.01,pulse_seconds=duration)
        b=p.waveform(t+h,.01,pulse_seconds=duration)
        m=p.waveform(t,.01,pulse_seconds=duration)
        for i in range(3):assert (b[i]-a[i])/(2*h)==pytest.approx(m[i+1],abs=1e-6)
    assert p.waveform(duration/2,.01,pulse_seconds=duration)[2]==pytest.approx(-4*.01*(math.pi/duration)**2)

@pytest.mark.parametrize("duration,amplitude",((.45,.02),(.45,-.03),(.2,.005),(float('nan'),.005),(True,.005)))
def test_unsafe_or_unlisted_waveform_rejected_before_arm(duration,amplitude):
    rig,clock=scripted_rig()
    with patch('cartpole_sdk.rig.client.time',clock),patch.object(p,'time',clock):
        with pytest.raises(ValidationError):p.run_pulse(rig,amplitude_m=amplitude,pulse_seconds=duration,hold_seconds=3.)
    assert not any(c[1]=='ARM' for c in rig.commands)
    assert rig.commands[-1][1]=='STOP'

@pytest.mark.parametrize("duration",(.45,.8,1.))
def test_real_runner_records_duration_quiet_second_and_unchanged_lease(duration):
    rig,clock=scripted_rig();ready=[]
    with patch('cartpole_sdk.rig.policy.time',clock),patch('cartpole_sdk.rig.client.time',clock),patch.object(p,'time',clock):
        result=p.run_pulse(rig,amplitude_m=.005,pulse_seconds=duration,hold_seconds=3.,ready=lambda info:ready.append(clock.now_ns))
    start=next(r for r in rig.records if r['type']=='ringdown_start')
    assert start['pulse_s']==duration and start['quiet_preflight_s']==1.
    assert ready[0]>=1_000_000_000
    assert duration+3.<=result['policy']['elapsed_board_s']<duration+3.05
    refs=[r for r in rig.records if r['type']=='ringdown_reference']
    assert refs[-1]['phase']=='feedback_cart_hold'
    actions=[r['request'] for r in rig.records if r['type']=='action_request']
    assert all(a['expires_at_ns']-a['issued_at_ns']==20_000_000 and abs(a['acceleration_m_s2'])<=3. for a in actions)
    assert not rig.state.enabled and rig.commands[-1][1]=='STOP'

def test_cli_rejects_unsafe_pair_without_serial_or_output(tmp_path):
    from cartpole_sdk.identification.cli import main,parser
    args=['collect-pulse','--execute','--port','offline','--amplitude-mm','20','--pulse-seconds','.45','--no-camera','--output',str(tmp_path/'bad')]
    assert parser().parse_args(args).pulse_seconds==.45
    with patch('cartpole_sdk.rig.Rig',side_effect=AssertionError('serial opened')):assert main(args)==2
    assert not (tmp_path/'bad').exists()
