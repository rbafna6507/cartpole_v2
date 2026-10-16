"""Trusted stopped tunables preserve provenance, coupled guards and old profiles."""
from dataclasses import asdict, replace
import json
import math
import struct
from pathlib import Path
import tempfile
import unittest

from cartpole_sdk.contracts import ValidationError
from cartpole_sdk.control import ControllerParameters, ReferenceController, load_tuned_parameters
from cartpole_sdk.control.motion import State, advance
from cartpole_sdk.control.reference import RailRecovery, can_capture
from cartpole_sdk.control.parameters import Gains
from cartpole_sdk.rig import Rig, RigError
from cartpole_sdk.rig.parameters import parameter_value, parameter_map, validate_parameters
from test_rig import FDTransport
from test_rig_parameters import ParameterFirmware

NEW_DEFAULTS = dict(manual_speed_max=.15, rail_fraction=.95, rail_margin=.015,
    rail_fault_margin=.010, rail_hysteresis=.005, rail_recover_v=.15,
    rail_recover_a=1.5, rail_recover_s=8., rehome_v=.08, rehome_a=.5, rehome_j=10.)

class TunableFirmware(ParameterFirmware):
    def __init__(self):
        self.version='executor-v6-measuredrail'
        self.x=.01
        self.rail_preference=.375
        super().__init__()
        self.values.update(NEW_DEFAULTS)
    def state(self,**kwargs):
        fields=super().state(**kwargs).split()
        fields[10]=str(self.x)
        return ' '.join(fields)
    def command(self,payload):
        p=payload.split()
        if p[1]=='INFO':
            self.commands.append(p)
            self.send(f'V2 INFO {self.sid} {self.version} 351 1 32 0 1 {self.span} {self.values["rail"]:.9g} 768 768 1 2300 0 0')
            return
        if p[1]=='PARAM':
            name=p[3]
            if name not in self.values:
                self.commands.append(p);self.send(f'V2 ERR {self.sid} parameter');return
            if len(p)==5 and self.version=='executor-v6-measuredrail':
                v=dict(self.values,**{name:float(p[4])})
                if (v['rail_fault_margin']>=v['rail_margin'] or
                    v['rail_margin']-v['rail_fault_margin']<.001-1e-9 or
                    v['vman']>v['manual_speed_max']):
                    self.commands.append(p);self.send(f'V2 ERR {self.sid} value');return
        super().command(payload)
        if p[1]=='PARAM' and len(p)==5 and self.version=='executor-v6-measuredrail':
            if p[3]=='rail':self.rail_preference=float(p[4])
            if p[3] in ('rail_fraction','rail_margin'):
                half=self.span//2
                cap=math.floor(half*self.values['rail_fraction']+self.values['rail_margin']*26666.6666667)/26666.6666667 if self.span else .26
                self.values['rail']=min(self.rail_preference,half/26666.6666667,cap) if self.span else min(self.rail_preference,cap)

class TunableRigTests(unittest.TestCase):
    def setUp(self):
        self.fw=TunableFirmware();self.addCleanup(self.fw.close)
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
    def rig(self):
        return Rig(self.fw.port,transport_factory=FDTransport,command_timeout=.2)
    def profile(self,values):
        p=Path(self.tmp.name)/'profile.json'
        p.write_text(json.dumps(dict(schema_version=1,parameters=values)))
        return p
    def test_all_supported_values_save_without_replacing_legacy_missing_values(self):
        with self.rig() as rig:
            self.fw.values['rehome_j']=13
            p=Path(self.tmp.name)/'saved.json';rig.save_parameters(p)
            self.assertEqual(json.loads(p.read_text())['parameters']['rehome_j'],13)
            self.assertEqual(len(rig.get_parameters()),41)
            rig.load_parameters(self.profile({'ke':3.5}))
            self.assertEqual(self.fw.values['rehome_j'],13)
            self.assertEqual([n for n,_ in self.fw.writes],['ke'])
    def test_legacy_catalog_is_read_live_and_new_keys_fail_before_writes(self):
        self.fw.version='executor-v5-calmodel'
        self.fw.values={k:v for k,v in self.fw.values.items() if k not in NEW_DEFAULTS}
        with self.rig() as rig:
            self.assertEqual(len(rig.get_parameters()),30)
            self.assertNotIn('manual_speed_max',rig.get_parameters())
            with self.assertRaisesRegex((RigError,ValidationError),'(?i)(unsupported|firmware)'):
                rig.load_parameters(self.profile({'ke':3,'rail_margin':.02}))
            self.assertFalse(self.fw.writes)
            self.assertIsNone(rig.error)
            self.assertEqual(rig.load_parameters(self.profile({'ke':3})),{'ke':3})
    def test_margin_pair_is_prevalidated_and_sequenced_both_directions(self):
        with self.rig() as rig:
            with self.assertRaises(ValidationError):
                rig.load_parameters(self.profile({'ke':3,'rail_fault_margin':.0145}))
            self.assertFalse(self.fw.writes)
            rig.load_parameters(self.profile({'rail_fault_margin':.025,'rail_margin':.03}))
            self.assertEqual([n for n,_ in self.fw.writes],['rail_margin','rail_fault_margin'])
            self.fw.writes.clear()
            rig.load_parameters(self.profile({'rail_margin':.015,'rail_fault_margin':.01}))
            self.assertEqual([n for n,_ in self.fw.writes],['rail_fault_margin','rail_margin'])
    def test_manual_limit_profile_sequence_and_active_intents_use_live_ceiling(self):
        with self.rig() as rig:
            rig.load_parameters(self.profile({'vman':.4,'manual_speed_max':.5}))
            self.assertEqual([n for n,_ in self.fw.writes],['manual_speed_max','vman'])
            rig.start('manual',.5)
            self.assertGreater(rig.set_velocity(.4),0)
            with self.assertRaises(ValidationError):rig.set_velocity(.501)
            self.assertEqual(rig.action_limits.max_abs_acceleration,25)
            rig.stop();self.fw.writes.clear()
            rig.load_parameters(self.profile({'manual_speed_max':.1,'vman':.05}))
            self.assertEqual([n for n,_ in self.fw.writes],['vman','manual_speed_max'])
            rig.start('manual',.5)
            with self.assertRaises(ValidationError):rig.set_velocity(.11)
    def test_direct_acceleration_reads_configured_native_ceiling_without_widening_broker(self):
        with self.rig() as rig:
            rig.set_parameter('amax_s',100)
            rig.set_parameter('amax_b',70)
            rig.arm(.5)
            self.assertGreater(rig.set_acceleration(90),0)
            with self.assertRaises(ValidationError):rig.set_acceleration(101)
            self.assertEqual(rig.action_limits.max_abs_acceleration,25)
    def test_geometry_shrink_excluding_current_cart_is_rejected_before_any_write(self):
        self.fw.x=.20
        with self.rig() as rig:
            with self.assertRaisesRegex(ValidationError,'(?i)(position|rehome|boundary)'):
                rig.load_parameters(self.profile({'ke':3,'rail':.19}))
            self.assertFalse(self.fw.writes)
    def test_geometry_only_profile_preserves_unobservable_future_home_preference(self):
        self.fw.span=16509
        with self.rig() as rig:
            result=rig.load_parameters(self.profile({'rail_fraction':.6}))
            self.assertEqual([n for n,_ in self.fw.writes],['rail_fraction'])
            self.assertEqual(self.fw.rail_preference,.375)
            self.assertAlmostEqual(result['rail'],.2007,places=4)
            self.fw.writes.clear()
            rig.load_parameters(self.profile({'rail_fraction':.95}))
            self.assertEqual([n for n,_ in self.fw.writes],['rail_fraction'])
            self.assertGreater(self.fw.values['rail'],.30)
            self.assertEqual(self.fw.rail_preference,.375)

    def test_geometry_derived_rail_is_reported_on_partial_failure(self):
        self.fw.span=16509
        self.fw.drop_write_reply='kpx'
        with self.rig() as rig:
            with self.assertRaises(RigError) as caught:
                rig.load_parameters(self.profile({'rail_fraction':.6,'kpx':35}))
            self.assertIn('rail_fraction',caught.exception.changed_parameters)
            self.assertAlmostEqual(caught.exception.changed_parameters['rail'],.2007,places=4)
            self.assertEqual(caught.exception.unconfirmed_parameter,'kpx')
    def test_margin_and_rail_expansion_can_use_safe_temporary_bridge(self):
        self.fw.span=16509
        self.fw.values['rail']=.025
        self.fw.rail_preference=.025
        with self.rig() as rig:
            result=rig.load_parameters(self.profile({'rail':.3095,'rail_margin':.05}))
            self.assertAlmostEqual(result['rail'],.3095,places=6)
            self.assertEqual([n for n,_ in self.fw.writes],['rail','rail_margin','rail'])

    def test_margin_geometry_invalid_profile_never_partially_writes(self):
        with self.rig() as rig:
            with self.assertRaises(ValidationError):
                rig.load_parameters(self.profile({'ke':3,'rail':.025,'rail_margin':.03}))
            self.assertFalse(self.fw.writes)

class TunableReferenceTests(unittest.TestCase):
    def test_expanded_numeric_envelopes_reject_nonfinite_and_hardware_overflow(self):
        for name,value in [('vmax',2),('vman',.4),('amax_s',200),('amax_m',150),
                           ('jmax',10000),('jmax_m',9000),('catch_da',200),
                           ('manual_speed_max',2),('rail_recover_v',2),('rehome_j',10000)]:
            with self.subTest(name=name):self.assertAlmostEqual(parameter_value(name,value),value)
        for name,value in [('vmax',2.68),('manual_speed_max',0),('amax_s',201),
                           ('jmax',10001),('rail_fraction',.991),('rail_fault_margin',.05)]:
            with self.subTest(name=name),self.assertRaises(ValidationError):parameter_value(name,value)
    def test_custom_margin_changes_braking_but_default_behavior_is_retained(self):
        args=(State(),.24,1,1.5,25,25,150,.26,.001)
        self.assertEqual(advance(*args).brake_direction,0)
        self.assertEqual(advance(*args,rail_margin=.025).brake_direction,1)
    def test_custom_hard_margin_and_recovery_fields_are_used(self):
        p=replace(load_tuned_parameters(),rail_margin=.03,rail_fault_margin=.02,
                  rail_hysteresis=.01,rail_recover_v=.08,rail_recover_a=.4,rail_recover_s=.1)
        c=ReferenceController(p)
        self.assertEqual(c.tick(3,.241,now_us=0,command='manual').mode,4)
        c.reset(3)
        o=c.tick(3,.231,now_us=0,command='manual')
        self.assertEqual(o.mode,6)
        self.assertAlmostEqual(c.rail.exit_boundary,.22)
        self.assertLessEqual(abs(o.demand),.400001)
        for i in range(1,110):o=c.tick(3,.231,now_us=i*1000)
        self.assertEqual(o.mode,4)
    def test_coupled_one_step_guard_rounds_each_operation_like_firmware(self):
        values=asdict(ControllerParameters())
        values.update(rail=.021037500351667404,rail_margin=.004999999888241291,
                      rail_hysteresis=.01600000075995922,rail_fault_margin=.004)
        # Native float32 subtraction leaves 0.00003750063478946686 m,
        # just above its one-step threshold; double subtraction rejects it.
        validate_parameters(parameter_map(values))
        values['rail']=.021037498489022255
        with self.assertRaises(ValidationError):validate_parameters(parameter_map(values))

    def test_capture_gate_uses_twice_the_configured_normal_margin(self):
        p=replace(load_tuned_parameters(),rail=.1,rail_margin=.03)
        # With zero feedback and zero angle/rate the forecast stays stationary;
        # x=.045 is outside the .1 - 2*.03 capture gate, despite being inside
        # the normal rail boundary. This isolates the configured geometry gate.
        self.assertFalse(can_capture(p,Gains(0,0,0,0),0,0,.045,0))
        self.assertTrue(can_capture(p,Gains(0,0,0,0),0,0,.035,0))

    def test_constructor_rejects_invalid_coupled_limits(self):
        for values in [dict(rail_margin=.015,rail_fault_margin=.0145),
                       dict(manual_speed_max=.01,vman=.05),dict(rail=.025,rail_margin=.03)]:
            with self.subTest(values=values),self.assertRaises(ValueError):ControllerParameters(**values)
