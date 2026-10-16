"""Native tests compile the production executor safety/protocol/homing headers."""
from pathlib import Path
import subprocess
import shutil
import tempfile
import unittest
import json
import re
ROOT = Path(__file__).resolve().parents[1]
FW = ROOT / 'firmware/teensy_executor'

class SourceTests(unittest.TestCase):
    def test_executor_source_exists(self):
        self.assertTrue((FW / 'executor_core.h').is_file(), 'production executor safety core missing')

    def test_preserved_algorithm_headers(self):
        archive = ROOT / 'archive/good_balancing_jetson/teensy_firmware/teensy_swingup'
        # Runtime-tunable extensions retain default behavior through the native
        # preserved_defaults case; all other archive headers remain byte-exact.
        extended={'cart_motion.h','rail_recovery.h','swing_controller.h'}
        for path in archive.glob('*.h'):
            if path.name in extended:continue
            self.assertEqual((FW / path.name).read_bytes(), path.read_bytes(), path.name)

    def test_saved_defaults_exclude_historical_calibration(self):
        settings = json.loads((ROOT / 'archive/good_balancing_jetson/settings.json').read_text())['settings']
        source = (FW / 'teensy_executor.ino').read_text()
        for name, value in settings.items():
            prefix = 'p_' if name.startswith('z') else 'controller.'
            match = re.search(r'  ' + re.escape(prefix + name) + r'=([-0-9.]+)f;', source)
            self.assertIsNotNone(match, name)
            self.assertEqual(float(match.group(1)), value, name)
        self.assertNotIn('1411', source)

class ExecutorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='executor-tests-')
        cls.binary = Path(cls.temp.name) / 'executor-tests'
        result = subprocess.run([shutil.which('c++') or '/usr/bin/c++', '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror', '-I', str(FW), str(ROOT / 'tests/executor_native/core.cpp'), '-o', str(cls.binary)], capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)
    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()
    def run_case(self, case):
        result = subprocess.run([str(self.binary), case], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

for name in ['calibration_guards','cart_only_switches','info_guards','homing_more_faults','stable_switches','framing','boot_session','actions','wrap','guards','watchdogs','switches','homing_success','homing_faults']:
    setattr(ExecutorTests, 'test_' + name, lambda self, name=name: self.run_case(name))

class SketchTests(ExecutorTests):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='executor-sketch-')
        build = Path(cls.temp.name)
        source = (FW / 'teensy_executor.ino').read_text()
        before = '  uint32_t mask;asm volatile("mrs %0, primask" : "=r"(mask) :: "memory");return mask;'
        if source.count(before) != 1:
            raise AssertionError('native ARM interrupt mask substitution must match once')
        (build / 'firmware_native.ino').write_text(source.replace(before, '  return native_interrupt_mask();', 1))
        cls.binary = build / 'executor-sketch'
        result = subprocess.run([shutil.which('c++') or '/usr/bin/c++', '-std=c++17', '-O2', '-fno-fast-math', '-I', str(ROOT / 'tests/executor_native'), '-I', str(ROOT / 'tests/native'), '-I', str(FW), '-I', str(build), str(ROOT / 'tests/executor_native/sketch.cpp'), '-o', str(cls.binary)], capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)

# Do not inherit the pure-header case names into the separate whole-sketch binary.
for name in ['calibration_guards','cart_only_switches','info_guards','homing_more_faults','stable_switches','framing','boot_session','actions','wrap','guards','watchdogs','switches','homing_success','homing_faults']:
    setattr(SketchTests, 'test_' + name, None)
for name in ['encoder_config_info_guard','encoder_config_boot','encoder_config_failed_write','encoder_config_failed_read','encoder_config_runtime','encoder_config_watchdog','encoder_config_recovery','encoder_config_stale','calibrate_cancel_commit_stop','calibrate_cancel_commit_hello','calibrate_upright','calibrate_hanging','calibrate_cancel','calibrate_fail_moving','calibrate_fail_magnet','calibrate_fail_save','calibrate_fail_watchdog','cart_only_pulses','lcd_health','magnet_stale','whole_homing_info','magnet_healthy','magnet_weak','magnet_strong','magnet_absent','magnet_readfailure','magnet_anglefailure','info_snapshot','info_homed','edge_consume_race','hello_partial','bounced_isr_edge','isr_center','calibration','reference_watchdog','motion','timing','isr_homing_stall','isr_limits','telemetry']:
    setattr(SketchTests, 'test_' + name, lambda self, name=name: self.run_case(name))


def _wire_contract(self):
    from cartpole_sdk.rig.protocol import decode, parse_state
    output = subprocess.run([str(self.binary), 'wire'], check=True, capture_output=True, text=True).stdout
    line = next(line for line in output.splitlines() if line.startswith('@')).encode('ascii') + b'\n'
    state = parse_state(decode(line), received_ns=123)
    self.assertEqual((state.sid, state.tick, state.us, state.mode), (7, 1, 11000, 12))
    self.assertTrue(state.enabled and state.homed and state.healthy)
    self.assertFalse(state.switch_profile)
    self.assertEqual((state.last_seq, state.fault, state.demand), (1, 0, 2.0))
    self.assertAlmostEqual(state.acceleration, .15, places=6)
SketchTests.test_sdk_wire_contract = _wire_contract

# Parameter cases use the same production core and complete native sketch.
ExecutorTests.test_parameter_core_guards = lambda self: self.run_case('parameter_core_guards')
SketchTests.test_parameter_core_guards = None
for name in ('parameter_values','parameter_bounds','parameter_guards','parameter_rail','measured_rail_motion'):
    setattr(SketchTests, 'test_' + name, lambda self, name=name: self.run_case(name))

ExecutorTests.test_homing_duration = lambda self: self.run_case('homing_duration')
SketchTests.test_homing_duration = None

for name in ('rehome_core_guards','auto_return_intent','return_safety_precedence'):
    setattr(ExecutorTests, 'test_' + name, lambda self, name=name: self.run_case(name))
    setattr(SketchTests, 'test_' + name, None)
for name in ('rehome_run','auto_return_braking','return_cancel','rehome_timeout','rehome_isr_limit','auto_expiry_fresh_health','rehome_completion_snapshot','rehome_configured_speed'):
    setattr(SketchTests, 'test_' + name, lambda self, name=name: self.run_case(name))

ExecutorTests.test_hanging_offset_core = lambda self: self.run_case('hanging_offset_core')
SketchTests.test_hanging_offset_core = None
for name in ('hanging_offset_capture','hanging_offset_cancel','hanging_model_quality'):
    setattr(SketchTests,'test_'+name,lambda self,name=name:self.run_case(name))

for name in ('tunable_motion','tunable_geometry','tunable_recovery','tunable_auto_return','preserved_defaults'):
    setattr(SketchTests,'test_'+name,lambda self,name=name:self.run_case(name))
