"""Offline bounds, controller guards and real-runner cleanup; never open serial."""
from dataclasses import asdict, replace
import importlib.util
import math
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from cartpole_sdk.contracts import Observation,Sample,Session,UNITS,ValidationError
from cartpole_sdk.control.parameters import ControllerParameters

PATH=Path(__file__)
from cartpole_sdk.identification import experiments as probe

def observation(ms=0, *, x=0.,v=0.,theta=math.pi,omega=0.,sequence=None):
    values=(x,v,theta,omega)
    samples=tuple(Sample(c.entity,c.quantity,c.source,value,UNITS[c.quantity],c.frame_id,
        'fixture','valid',None,'estimated',ms*1_000_000,ms*1_000_000,ms*1_000_000)
        for c,value in zip(probe.CHANNELS,values))
    return Observation('7','teensy:7',ms if sequence is None else sequence,ms*1_000_000,'fixture',samples)

def policy(amplitude=.01):
    clock=[0]
    p=probe.RingdownPolicy(probe.CHANNELS,amplitude_m=amplitude,initial_hanging=math.pi,clock_ns=lambda:clock[0])
    p.reset(Session('7','teensy:7'))
    return p,clock

@pytest.mark.parametrize('amplitude',(-.03,-.02,-.01,-.005,.005,.01,.02,.03))
def test_endpoints_derivatives_and_exact_continuous_bounds(amplitude):
    for t in (-1,0,.65,.66,15):assert probe.waveform(t,amplitude)==(0.,)*4
    for t in (.05,.17,.325,.51,.61):
        h=1e-6;left=probe.waveform(t-h,amplitude);right=probe.waveform(t+h,amplitude);mid=probe.waveform(t,amplitude)
        for i in range(3):assert (right[i]-left[i])/(2*h)==pytest.approx(mid[i+1],abs=1e-7)
    bounds=probe.waveform_bounds(amplitude)
    w=math.pi/.65;A=abs(amplitude)
    assert bounds['analytic_abs_max'][0]==A
    assert bounds['analytic_abs_max'][1]==pytest.approx(3*math.sqrt(3)/4*A*w)
    assert bounds['analytic_abs_max'][2]==pytest.approx(4*A*w*w)
    for measured,bound in zip(bounds['grid_abs_max'],bounds['analytic_abs_max']):
        assert measured<=bound*(1+1e-12)
        assert measured>=bound*.99999
    assert bounds['analytic_abs_max'][1]<.19
    assert bounds['analytic_abs_max'][2]<2.81
    assert bounds['analytic_abs_max'][3]<38

@pytest.mark.parametrize('amplitude',(0,.006,.015,.04,float('nan'),float('inf'),True))
def test_exact_amplitude_allowlist(amplitude):
    with pytest.raises((ValidationError,ValueError)):policy(amplitude)


def test_perfect_tracking_then_feedback_hold_and_clamp_metadata():
    p,clock=policy(.03)
    for i in range(1266):
        t=i/100;clock[0]=i*10_000_000;x,v,a,_=probe.waveform(t,.03)
        command=p.act(observation(i*10,x=x,v=v)).acceleration_m_s2
        assert command==pytest.approx(a)
    assert p.mode=='feedback_cart_hold' and p.clamped_commands==0
    clock[0]+=10_000_000
    assert p.act(observation(12660,x=.002,v=.003)).acceleration_m_s2==pytest.approx(-.202)
    clock[0]+=10_000_000
    assert p.act(observation(12670,x=.04,v=.2)).acceleration_m_s2==-3.
    assert p.clamped_commands==1

@pytest.mark.parametrize('values',({'x':.05},{'x':-.05},{'v':.3},{'v':-.3},
    {'theta':math.pi+1.},{'theta':math.pi-1.},{'omega':10.},{'omega':-10.}))
def test_measured_guards_fail_before_new_command(values):
    p,clock=policy();p.act(observation());clock[0]+=10_000_000
    with pytest.raises(ValidationError,match='trajectory'):p.act(observation(10,**values))

@pytest.mark.parametrize('kind',('board','host','replay','backwards','stale','source','skew'))
def test_cadence_replay_and_sensor_guards(kind):
    p,clock=policy();p.act(observation());clock[0]=10_000_000;o=observation(10)
    if kind=='board':o=observation(20)
    if kind=='host':clock[0]=20_000_000
    if kind=='replay':o=observation(10,sequence=0)
    if kind=='backwards':o=observation(0,sequence=1)
    if kind=='stale':o=replace(o,available_ns=30_000_000)
    if kind=='source':o=replace(o,samples=(replace(o.samples[0],source='vision'),)+o.samples[1:])
    if kind=='skew':o=replace(o,samples=(replace(o.samples[0],effective_ns=9_000_000),)+o.samples[1:])
    with pytest.raises(ValidationError):p.act(o)


def test_preflight_requires_exact_epoch_reference_and_released_switches():
    state=SimpleNamespace(healthy=True,homed=True,switch_profile=True,flags=205,enabled=False,
        mode=0,x=0.,velocity=0.,acceleration=0.,omega=0.,theta=math.pi,brake_direction=0)
    info=SimpleNamespace(firmware='executor-v6-measuredrail',encoder_upright_raw=330,
        reference_saved=True,encoder_conf_valid=True,home_epoch=14)
    probe.validate_preflight(state,info)
    for key,value in (('flags',221),('enabled',True),('healthy',False),('homed',False),
        ('switch_profile',False),('x',.003),('velocity',.005),('acceleration',.1),('omega',.15),('theta',0.),('brake_direction',1)):
        with pytest.raises(ValidationError):probe.validate_preflight(SimpleNamespace(**(vars(state)|{key:value})),info)
    for key,value in (('home_epoch',0),('encoder_upright_raw',4096),('reference_saved',False),('encoder_conf_valid',False)):
        with pytest.raises(ValidationError):probe.validate_preflight(state,SimpleNamespace(**(vars(info)|{key:value})))


def scripted_rig():
    root=PATH.parents[1];sys.path.insert(0,str(root/'tests'))
    from test_rig_console import ScriptedClock,ScriptedConsoleRig
    clock=ScriptedClock();clock.now_ns=0
    rig=ScriptedConsoleRig('offline-ringdown',clock=clock,rate_hz=100,record_capacity=8192)
    rig.connect();rig._state=replace(rig._state,theta=math.pi,angle_hat=math.pi,omega=0.,x=0.,flags=205)
    rig._info=SimpleNamespace(firmware='executor-v6-measuredrail',encoder_upright_raw=330,
        reference_saved=True,encoder_conf_valid=True,home_epoch=14)
    return rig,clock

@pytest.mark.parametrize('failure_kind',(None,'wait','guard','stop','original_and_stop','preflight'))
def test_real_runner_stop_and_fault_cleanup_without_native_mode_or_recovery(failure_kind):
    rig,clock=scripted_rig();original_wait=rig.wait_state;original_stop=rig.stop
    error=RuntimeError('injected wait failure');stops=[]
    def wait(*args,**kw):
        if rig.state.enabled and failure_kind in ('wait','original_and_stop'):raise error
        state=original_wait(*args,**kw)
        if rig.state.enabled and failure_kind=='guard':rig._state=replace(state,x=.05)
        return rig.state
    def stop():
        stops.append(True);original_stop()
        if failure_kind in ('stop','original_and_stop'):raise RuntimeError('injected stop failure')
    rig.wait_state=wait;rig.stop=stop
    if failure_kind=='preflight':rig._info.home_epoch=0
    with patch('cartpole_sdk.rig.policy.time',clock),patch('cartpole_sdk.rig.client.time',clock),patch.object(probe,'time',clock):
        try:
            if failure_kind:
                with pytest.raises(Exception) as caught:probe.run_pulse(rig,amplitude_m=.01)
                if failure_kind=='original_and_stop':assert caught.value is error
            else:result=probe.run_pulse(rig,amplitude_m=.01)
        finally:rig.close()
    assert stops and not rig.state.enabled
    assert not any(c[1] in ('MODE','HOME','REHOME','CALIBRATE','CLEAR','SET') for c in rig.commands)
    actions=[r['request'] for r in rig.records if r['type']=='action_request']
    if failure_kind=='preflight':assert not actions and not any(c[1]=='ARM' for c in rig.commands)
    elif failure_kind in (None,'stop'):
        assert len(actions)>1200
        assert all(a['expires_at_ns']-a['issued_at_ns']==20_000_000 and abs(a['acceleration_m_s2'])<=3 for a in actions)
        refs=[r for r in rig.records if r['type']=='ringdown_reference']
        assert refs[-1]['phase']=='feedback_cart_hold' and refs[-1]['t_s']>=12.65
        assert all('host_policy_ns' in r and 'clamped' in r for r in refs)


def test_incomplete_parameter_catalog_stops_before_arming():
    rig,clock=scripted_rig();values=asdict(ControllerParameters());values.pop('jmax')
    rig.get_parameters=lambda:values
    with patch('cartpole_sdk.rig.client.time',clock),patch.object(probe,'time',clock):
        try:
            with pytest.raises(ValidationError,match='41-parameter'):probe.run_pulse(rig,amplitude_m=.005)
        finally:rig.close()
    assert any(c[1]=='STOP' for c in rig.commands)
    assert not any(c[1]=='ARM' for c in rig.commands)

@pytest.mark.parametrize('changed',({'flags':221},{'healthy':False},{'homed':False},{'switch_profile':False},{'mode':3}))
def test_runtime_health_home_switch_and_mode_rejections(changed):
    state=SimpleNamespace(healthy=True,homed=True,switch_profile=True,flags=207,mode=12)
    with pytest.raises(ValidationError):probe.validate_board(SimpleNamespace(**(vars(state)|changed)))



def test_saved_reference_home_are_generic_but_optional_pins_are_exact():
    rig,clock=scripted_rig();rig._info.encoder_upright_raw=1234;rig._info.home_epoch=8
    probe.validate_preflight(rig.state,rig.get_info())
    with pytest.raises(ValidationError,match='expected'):
        probe.validate_preflight(rig.state,rig.get_info(),expected_reference=330)
    with pytest.raises(ValidationError,match='expected'):
        probe.validate_preflight(rig.state,rig.get_info(),expected_home=14)
    probe.validate_preflight(rig.state,rig.get_info(),expected_reference=1234,expected_home=8)


def test_passive_session_never_arms_and_stops_on_midstream_health_loss():
    rig,clock=scripted_rig();original=rig.wait_state
    def wait(*a,**kw):
        state=original(*a,**kw)
        if clock.now_ns>550_000_000:rig._state=replace(state,flags=state.flags&~4)
        return rig.state
    rig.wait_state=wait
    with patch('cartpole_sdk.rig.client.time',clock),patch.object(probe,'time',clock):
        with pytest.raises(ValidationError):probe.run_passive(rig,seconds=1.)
    assert not any(c[1] in ('ARM','MODE','HOME','REHOME','CLEAR','CALIBRATE') for c in rig.commands)
    assert rig.commands[-1][1]=='STOP' and not rig.state.enabled


def test_missing_camera_prevents_serial_open_and_preserves_failure(tmp_path):
    class MissingCamera:
        def __init__(self,*a,**kw):pass
        def start(self):raise RuntimeError('camera unavailable')
        def close(self):return {'failure':'camera unavailable'}
    def rig_factory(*a,**kw):raise AssertionError('serial must not open without camera')
    output=tmp_path/'failed'
    with pytest.raises(RuntimeError,match='camera unavailable'):
        probe.collect('pulse',output=output,port='offline',amplitude_m=.005,
            camera_factory=MissingCamera,rig_factory=rig_factory)
    import json
    report=json.loads((output/'report.json').read_text())
    assert report['completed'] is False and 'camera unavailable' in report['failure']
    with pytest.raises(FileExistsError):probe.collect('pulse',output=output,port='offline',amplitude_m=.005)


def test_camera_failure_during_policy_stops_without_new_action():
    rig,clock=scripted_rig()
    def camera_check():
        if rig.state.enabled:raise RuntimeError('camera disconnected')
    with patch('cartpole_sdk.rig.policy.time',clock),patch('cartpole_sdk.rig.client.time',clock),patch.object(probe,'time',clock):
        with pytest.raises(RuntimeError,match='camera disconnected'):
            probe.run_pulse(rig,amplitude_m=.005,check=camera_check)
    assert not rig.state.enabled and rig.commands[-1][1]=='STOP'
    assert not any(c[1]=='A' for c in rig.commands)


@pytest.mark.parametrize('camera_enabled',(False,True))
def test_camera_collection_wires_current_session_encoder_mirror(tmp_path,camera_enabled):
    from cartpole_sdk.sensing.telemetry import EncoderPublisher
    seen={}
    class ReadyCamera:
        def __init__(self,*a):pass
        def start(self):pass
        def check(self):pass
        def close(self):return {'frames':1}
    def rig_factory(*a,**kwargs):
        seen.update(kwargs)
        raise RuntimeError('no serial in wiring test')
    with pytest.raises(RuntimeError,match='no serial'):
        probe.collect('pulse',port='offline',output=tmp_path/'run',camera_url=probe.DEFAULT_CAMERA_URL if camera_enabled else None,
            camera_factory=ReadyCamera,rig_factory=rig_factory)
    assert isinstance(seen.get('vision_publisher'),EncoderPublisher) is camera_enabled


def test_passive_readiness_is_announced_only_after_disabled_preflight():
    rig,clock=scripted_rig();ready=[]
    def announce(data):
        ready.append(data)
        assert not rig.state.enabled and rig.state.mode==0
    with patch('cartpole_sdk.rig.client.time',clock),patch.object(probe,'time',clock):
        probe.run_passive(rig,seconds=1.,ready=announce)
    assert ready[0]['status']=='recording' and ready[0]['drivers_enabled'] is False
    assert not any(c[1]=='ARM' for c in rig.commands)


def test_explicit_short_feedback_hold_changes_duration_without_changing_lease():
    rig,clock=scripted_rig()
    with patch('cartpole_sdk.rig.policy.time',clock),patch('cartpole_sdk.rig.client.time',clock),patch.object(probe,'time',clock):
        result=probe.run_pulse(rig,amplitude_m=.005,hold_seconds=3.)
    start=next(r for r in rig.records if r['type']=='ringdown_start')
    assert start['feedback_hold_s']==3. and start['pulse_s']==.65
    assert 3.65<=result['policy']['elapsed_board_s']<3.70
    actions=[r['request'] for r in rig.records if r['type']=='action_request']
    assert 360<len(actions)<375
    assert all(a['expires_at_ns']-a['issued_at_ns']==20_000_000 for a in actions)
    assert not rig.state.enabled and rig.commands[-1][1]=='STOP'

@pytest.mark.parametrize('hold',(2.99,12.01,float('nan'),True))
def test_invalid_hold_stops_before_arming(hold):
    rig,clock=scripted_rig()
    with patch('cartpole_sdk.rig.client.time',clock),patch.object(probe,'time',clock):
        with pytest.raises(ValidationError):probe.run_pulse(rig,amplitude_m=.005,hold_seconds=hold)
    assert not any(c[1]=='ARM' for c in rig.commands)
    assert rig.commands[-1][1]=='STOP'


def camera_capture(tmp_path,rows):
    import io,json,threading
    stop=threading.Event();ready=threading.Event()
    class Stream(io.BytesIO):
        def readline(self,*a):
            line=super().readline(*a)
            if self.tell()==len(self.getvalue()):stop.set()
            return line
    stream=Stream(''.join(json.dumps(r)+'\n' for r in rows).encode())
    # EOF is not the test's termination: preserve a final valid sentinel so the
    # stale row under test is evaluated before stop is set.
    with patch('urllib.request.urlopen',return_value=stream):probe.record_camera('http://camera.test/stream',tmp_path,1.,stop,ready)
    return ready.is_set(),json.loads((tmp_path/'vision-report.json').read_text())


def camera_row(stream_seq=1,frame_seq=7,t=10.,host_t=10.01,**values):
    return dict(schema='cartpole-sensing-stream-v1',stream_seq=stream_seq,host_t=host_t,
        vision=dict(seq=frame_seq,t=t,stale=False,age_since_host_read_s=host_t-t,worker_error=None,**values))

@pytest.mark.parametrize('bad',('stale','worker','old','invalid_age','reversed_frame','reversed_host'))
def test_camera_source_freshness_not_heartbeat_liveness(tmp_path,bad):
    first=camera_row();broken=camera_row(2,8,10.02,10.03)
    if bad=='stale':broken['vision']['stale']=True
    if bad=='worker':broken['vision']['worker_error']='camera stalled'
    if bad=='old':broken=camera_row(2,7,10.,11.)
    if bad=='invalid_age':broken['vision']['age_since_host_read_s']=-1
    if bad=='reversed_frame':broken=camera_row(2,6,10.02,10.03)
    if bad=='reversed_host':broken=camera_row(2,8,9.99,10.)
    ready,report=camera_capture(tmp_path,[first,broken,camera_row(3,9,10.04,10.05)])
    assert ready and 'failure' in report


def test_stale_initial_camera_cannot_signal_ready(tmp_path):
    stale=camera_row();stale['vision'].update(stale=True,worker_error='camera stalled',age_since_host_read_s=9998.)
    ready,report=camera_capture(tmp_path,[stale,camera_row(2,8,10.02,10.03)])
    assert not ready and 'failure' in report


def test_bounded_fresh_duplicate_camera_heartbeat_is_preserved_not_a_new_frame(tmp_path):
    ready,report=camera_capture(tmp_path,[camera_row(),camera_row(2,7,10.,10.04),camera_row(3,8,10.05,10.06)])
    assert ready and 'failure' not in report
    assert report['frames']==2 and report['heartbeat_records']==1
