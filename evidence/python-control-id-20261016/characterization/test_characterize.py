"""Local numerical and protocol tests. No serial or hardware is opened."""
import dataclasses
import importlib.util
import contextlib
import io
import math
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from cartpole_sdk.contracts import Observation, Sample, Session, UNITS, ValidationError
from cartpole_sdk.control.parameters import ControllerParameters

PATH=Path(__file__).with_name('characterize.py')
SPEC=importlib.util.spec_from_file_location('characterize',PATH)
module=importlib.util.module_from_spec(SPEC) if SPEC else None
if PATH.exists(): SPEC.loader.exec_module(module)

def obs(ms=1000, *, x=0.,v=0.,theta=3.03,omega=0.,seq=None):
    samples=[]
    for entity,q,source,frame,value in [('cart','position','step','cart-step-home',x),('cart','velocity','step','cart-step-home',v),('pole','angle','magnetic','encoder-zero',theta),('pole','angular_velocity','magnetic','encoder-zero',omega)]:
        samples.append(Sample(entity,q,source,value,UNITS[q],frame,'fixture','valid',None,'estimated',ms*1_000_000,ms*1_000_000,ms*1_000_000))
    return Observation('7','teensy:7',ms if seq is None else seq,ms*1_000_000,'board acquisition snapshot proxy',tuple(samples))

class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(PATH.exists(),'characterization implementation is missing')
        self.clock=[1_000_000_000]
    def policy(self, **kw):
        p=module.CharacterizationPolicy(module.CHANNELS,kind='pilot',initial_hanging=3.03,clock_ns=lambda:self.clock[0],**kw)
        p.reset(Session('7','teensy:7'))
        return p
    def advance(self,p,milliseconds=10,**kw):
        self.clock[0]+=milliseconds*1_000_000
        return p.act(obs(1000+milliseconds,**kw))
    def test_waveform_endpoints_and_independent_derivatives(self):
        for kind in ('pilot','train','heldout'):
            for t in (-1,0,20,21):
                self.assertLess(max(abs(v) for v in module.waveform(t,kind)),1e-11)
            for t in (.2,1.5,2.,3.3,18.,19.8):
                h=1e-5;left=module.waveform(t-h,kind);right=module.waveform(t+h,kind);mid=module.waveform(t,kind)
                # Quintic taper is C2. At the ramp joins jerk can jump; a
                # centered difference there averages the two one-sided jerks.
                for j in range(2 if t in (2.,18.) else 3):
                    self.assertAlmostEqual((right[j]-left[j])/(2*h),mid[j+1],delta=2e-5)
                if t in (2.,18.):self.assertAlmostEqual(left[2],right[2],delta=.0002)
    def test_waveform_continuous_reference_bounds(self):
        result=module.waveform_bounds()
        for kind in ('pilot','train','heldout'):
            limits=(.00325,.0331,.31) if kind=='pilot' else (.007,.067,.63)
            for value,limit in zip(result[kind]['continuous_bounds'],limits):self.assertLess(value,limit)
        self.assertEqual(result['pilot']['amplitude_per_tone_m'],.00125)
        self.assertEqual(result['heldout']['frequencies_hz'],[.7,1.6,2.3])
    def test_feedback_uses_actual_position_velocity_and_clamps(self):
        p=self.policy();self.assertAlmostEqual(p.act(obs(x=.002,v=.002)).acceleration_m_s2,-.188)
        self.assertEqual(self.advance(p,x=.02,v=.1).acceleration_m_s2,-1.)
    def test_actual_trajectory_guards_stop_before_command(self):
        for values in ({'x':.030001},{'x':-.030001},{'v':.120001},{'v':-.120001},{'theta':3.03+.650001},{'theta':3.03-.650001},{'omega':6.00001},{'omega':-6.00001}):
            with self.subTest(values=values):
                p=self.policy();p.act(obs())
                with self.assertRaises(ValidationError):self.advance(p,**values)
    def test_angle_wrap_is_relative_to_initial_hanging(self):
        p=self.policy();p.act(obs())
        self.assertIsNotNone(self.advance(p,theta=-3.12))
    def test_board_host_duplicate_session_and_channel_failures(self):
        p=self.policy();p.act(obs())
        with self.assertRaises(ValidationError):self.advance(p,20)
        p=self.policy();p.act(obs());self.clock[0]+=20_000_000
        with self.assertRaises(ValidationError):p.act(obs(1010))
        p=self.policy();p.act(obs())
        with self.assertRaises(ValidationError):p.act(obs())
        p=self.policy()
        with self.assertRaises(ValidationError):p.act(dataclasses.replace(obs(),session_id='8'))
        for changed in (dataclasses.replace(obs().samples[0],validity='invalid',reason='lost home'),dataclasses.replace(obs().samples[0],effective_ns=979_000_000)):
            p=self.policy();bad=dataclasses.replace(obs(),samples=(changed,)+obs().samples[1:])
            with self.assertRaises(ValidationError):p.act(bad)
    def test_complete_waveform_and_zero_tail_are_bounded(self):
        traces=[];p=self.policy(tail=True,record=lambda **record:traces.append(record))
        for i in range(4001):
            t=i*.01;self.clock[0]=1_000_000_000+i*10_000_000
            x,v,a,_=module.waveform(t,'pilot')
            command=p.act(obs(1000+i*10,x=x,v=v)).acceleration_m_s2
            self.assertAlmostEqual(command,a if t<20 else 0.,delta=1e-12)
            self.assertLessEqual(abs(command),1.)
        self.assertEqual(traces[2000]['phase'],'commanded_hold')
        self.assertEqual(traces[-1]['phase'],'complete')
    def test_tail_rejects_cart_motion_at_taper_end(self):
        for values in ({'x':.003},{'v':.005}):
            p=self.policy(tail=True)
            for i in range(2000):
                self.clock[0]=1_000_000_000+i*10_000_000;p.act(obs(1000+i*10))
            self.clock[0]+=10_000_000
            with self.assertRaises(ValidationError):p.act(obs(21000,**values))
    def test_preflight_requires_reference_switches_home_and_quiet_down(self):
        state=SimpleNamespace(enabled=False,mode=0,healthy=True,homed=True,switch_profile=True,x=0.,velocity=0.,acceleration=0.,omega=0.,theta=3.03,brake_direction=0)
        info=SimpleNamespace(encoder_upright_raw=330,reference_saved=True,encoder_conf_valid=True)
        module.validate_preflight(state,info)
        for key,value in [('enabled',True),('mode',4),('healthy',False),('homed',False),('switch_profile',False),('x',.003),('velocity',.005),('acceleration',.1),('omega',.15),('theta',0.),('brake_direction',1)]:
            with self.subTest(key=key):
                changed=SimpleNamespace(**vars(state));setattr(changed,key,value)
                with self.assertRaises(ValidationError):module.validate_preflight(changed,info)
        info.encoder_upright_raw=331
        with self.assertRaises(ValidationError):module.validate_preflight(state,info)

class ProtocolTests(unittest.TestCase):
    def setUp(self):self.assertTrue(PATH.exists(),'characterization implementation is missing')
    def test_runner_is_bounded_and_failure_stops_without_recovery(self):
        class RigFixture:
            rate_hz=100
            session=Session('7','teensy:7')
            state=SimpleNamespace(enabled=False,mode=0,healthy=True,homed=True,switch_profile=True,x=0.,velocity=0.,acceleration=0.,omega=0.,theta=3.03,brake_direction=0,unwrapped_tick=1000)
            def __init__(self):self.stops=0;self.events=[]
            def _stopped_healthy(self):return self.state
            def get_info(self):return SimpleNamespace(encoder_upright_raw=330,reference_saved=True,encoder_conf_valid=True)
            def get_parameters(self):return dataclasses.asdict(ControllerParameters())
            def _fresh(self,state):pass
            def _observation(self,state):return obs()
            def _record(self,kind,**data):self.events.append((kind,data))
            def stop(self):self.stops+=1
        for injected_failure in (False,True):
            rig=RigFixture()
            def runner(rig_arg,factory,**kw):
                self.assertIs(rig_arg,rig)
                self.assertEqual(kw['channels'],module.CHANNELS)
                self.assertEqual(kw['ttl_ms'],20)
                self.assertEqual(kw['max_acceleration'],1.)
                self.assertLessEqual(kw['duration_s'],40.1)
                policy=factory(kw['channels']);policy.reset(rig.session)
                self.assertEqual(policy.act(kw['observation_provider']()).acceleration_m_s2,0.)
                if injected_failure:raise RuntimeError('injected runner failure')
            with patch.object(module,'run_policy',runner),patch.object(module,'stationary_preflight',lambda r,i:3.03):
                if injected_failure:
                    with self.assertRaisesRegex(RuntimeError,'injected runner failure'):module.run_characterization(rig,kind='pilot',tail=True)
                else:module.run_characterization(rig,kind='pilot',tail=True)
            self.assertEqual(rig.stops,1)
            self.assertTrue(any(e[0]=='characterization_start' for e in rig.events))
    def test_runtime_health_guard_rejects_loss_of_switches_or_home(self):
        for field in ('healthy','homed','switch_profile'):
            state=SimpleNamespace(healthy=True,homed=True,switch_profile=True)
            setattr(state,field,False)
            with self.subTest(field=field),self.assertRaises(ValidationError):module.validate_board(state)
    def test_cli_requires_explicit_hardware_arguments(self):
        with patch('cartpole_sdk.rig.Rig',side_effect=AssertionError('hardware opened')),contextlib.redirect_stderr(io.StringIO()):
            for args in ([],['--kind','pilot'],['--execute','--kind','pilot'],['--check-waveform','--execute']):
                with self.subTest(args=args),self.assertRaises(SystemExit) as caught:module.main(args)
                self.assertEqual(caught.exception.code,2)
    def test_sdk_protocol_stops_on_observed_boundary_without_mutating_configuration(self):
        # Real SDK/client and framed protocol over a local PTY, never a device.
        # Reuse the repository's independent test firmware and FD transport.
        sys.path.insert(0,str(PATH.parents[3]/'tests'))
        from test_rig_parameters import ParameterFirmware
        from test_rig import FDTransport
        from cartpole_sdk.rig import Rig
        class FixtureFirmware(ParameterFirmware):
            def __init__(self):
                super().__init__();self.flags=13
            def command(self,payload):
                p=payload.split()
                if p[1]=='INFO':
                    self.commands.append(p)
                    self.send(f'V2 INFO {self.sid} executor-v6-measuredrail 330 1 32 0 13 16502 0.308925 768 768 1 2300 0 0')
                    return
                super().command(payload)
            def state(self,**kw):
                p=super().state(**kw).split()
                p[7]=p[8]='3.03';p[9]=p[11]=p[12]='0'
                p[10]='.031' if sum(c[1]=='A' for c in self.commands)>=5 else '0'
                return ' '.join(p)
        fw=FixtureFirmware()
        try:
            with tempfile.TemporaryDirectory() as directory:
                with Rig(fw.port,rate_hz=100,log_dir=directory,transport_factory=FDTransport) as rig:
                    with self.assertRaisesRegex(ValidationError,'trajectory exceeded'):
                        module.run_characterization(rig,kind='pilot')
                    self.assertFalse(rig.state.enabled)
                actions=[c for c in fw.commands if c[1]=='A']
                self.assertEqual(len(actions),5)
                self.assertTrue(all(abs(float(c[6]))<=1. for c in actions))
                self.assertTrue(all(c[5]=='20' for c in actions))
                self.assertIn(['V2','RATE',str(fw.sid),'100'],fw.commands)
                self.assertFalse(fw.writes)
                self.assertFalse(any(c[1] in ('HOME','CENTER','CLEAR','SWITCHES','CAL','MODE','REHOME') for c in fw.commands))
                self.assertEqual({c[3] for c in fw.commands if c[1]=='PARAM'},set(fw.values))
        finally:fw.close()

if __name__=='__main__':unittest.main()
