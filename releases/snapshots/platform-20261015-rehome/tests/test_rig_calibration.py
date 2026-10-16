"""Deferred encoder calibration completion over a real PTY transport."""
from concurrent.futures import ThreadPoolExecutor
import io
import tempfile
import threading
import time
import unittest

from cartpole_sdk.contracts import ValidationError
from cartpole_sdk.rig import Rig, RigError
from cartpole_sdk.rig.console import execute_command, main
from cartpole_sdk.rig.protocol import decode
from test_rig import Firmware, FDTransport


class CalibrationFirmware(Firmware):
    def __init__(self):
        self.identity = 'executor-v2-cart2'
        self.reference = 3485
        self.saved = True
        self.delay = .15
        self.failure = None
        self.pending = False
        self.completed = False
        self.started = threading.Event()
        self.timer = None
        super().__init__()
        self.flags = 205  # Homed, healthy, switch profile enabled, unused 3/4 open.

    def command(self, payload):
        parts = payload.split()
        if parts[1] == 'INFO':
            self.commands.append(parts)
            diagnostics = ' 768 768 1 3210 50000 0' if self.identity in ('executor-v3-encguard','executor-v4-rehome') else ''
            self.send(f'V2 INFO {self.sid} {self.identity} {self.reference} {int(self.saved)} 103 0 2 13867 0.255'+diagnostics)
        elif parts[1] == 'CALIBRATE':
            self.commands.append(parts)
            self.pending = True
            self.flags |= 256
            self.started.set()
            if self.delay is not None:
                self.timer = threading.Timer(self.delay, self.finish)
                self.timer.start()
        else:
            if parts[1] == 'STOP':
                self.pending = False
                self.flags &= ~256
            super().command(payload)

    def finish(self):
        if not self.pending or self.done.is_set():
            return
        self.pending = False
        self.flags &= ~256
        if self.failure:
            self.send(f'V2 ERR {self.sid} {self.failure}')
        else:
            self.reference = 3210
            self.completed = True
            self.send(f'V2 OK {self.sid} CALIBRATE')

    def close(self):
        if self.timer is not None:
            self.timer.cancel()
            self.timer.join(.5)
        super().close()


class FastDeadlineRig(Rig):
    """Scale only the calibration wait while keeping real command/IO handling."""
    def _command(self, command, *args, **kwargs):
        if command == 'CALIBRATE':
            self.calibration_timeout = kwargs.get('timeout_s')
            kwargs['timeout_s'] = .08
        return super()._command(command, *args, **kwargs)


class InterruptTransport(FDTransport):
    def write(self, data):
        written = super().write(data)
        if decode(data).split()[1] == 'CALIBRATE':
            raise KeyboardInterrupt()
        return written


class RigCalibrationTests(unittest.TestCase):
    def setUp(self):
        self.fw = CalibrationFirmware()

    def tearDown(self):
        self.fw.close()

    def rig(self, port=None, *, rig_type=Rig, transport_factory=FDTransport, **kwargs):
        return rig_type(port or self.fw.port, transport_factory=transport_factory,
                        command_timeout=.1, **kwargs)

    def wait_until(self, predicate):
        deadline = time.monotonic() + .5
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(.002)
        self.fail('expected condition did not arrive')

    def test_success_waits_for_deferred_ack_then_reads_saved_reference(self):
        with self.rig() as rig, ThreadPoolExecutor(1) as pool:
            result = pool.submit(rig.calibrate_encoder)
            self.assertTrue(self.fw.started.wait(.5))
            time.sleep(.03)
            self.assertFalse(result.done())
            info = result.result(timeout=1)
            self.assertTrue(self.fw.completed)
            self.assertTrue(info.reference_saved)
            self.assertEqual(info.encoder_upright_raw, 3210)
            self.assertFalse(rig.state.enabled)
            self.assertTrue(rig.state.homed)
            self.assertTrue(rig.state.switch_profile)
            commands = [c for c in self.fw.commands if c[1] not in ('PING', 'STATUS')]
            self.assertEqual([c[1] for c in commands[-3:]], ['INFO', 'CALIBRATE', 'INFO'])
            self.assertEqual(commands[-2][3], 'upright')
            self.assertFalse(any(c[1] in ('ARM', 'MODE', 'CLEAR', 'CENTER', 'SWITCHES') for c in commands))

    def test_hanging_pose_works_without_streaming(self):
        with self.rig(rate_hz=0) as rig:
            self.assertEqual(rig.calibrate_encoder('hanging').encoder_upright_raw, 3210)
            self.assertEqual(next(c for c in self.fw.commands if c[1] == 'CALIBRATE')[3], 'hanging')

    def test_guard_firmware_calibration_returns_verified_reference_and_diagnostics(self):
        self.fw.identity = 'executor-v3-encguard'
        with self.rig() as rig:
            info = rig.calibrate_encoder('hanging')
            self.assertEqual(info.encoder_upright_raw, 3210)
            self.assertTrue(info.reference_saved)
            self.assertEqual(info.encoder_conf, 768)
            self.assertIs(info.encoder_conf_valid, True)
            self.assertEqual(next(c for c in self.fw.commands if c[1] == 'CALIBRATE')[3], 'hanging')
            self.assertFalse(rig.state.enabled)

    def test_unknown_pose_sends_no_calibration(self):
        with self.rig() as rig:
            for pose in ('down', '', None, True):
                with self.subTest(pose=pose), self.assertRaises(ValidationError):
                    rig.calibrate_encoder(pose)
            self.assertFalse(any(c[1] == 'CALIBRATE' for c in self.fw.commands))

    def test_legacy_firmware_fails_locally_with_update_instruction(self):
        self.fw.identity = 'executor-v1'
        with self.rig() as rig:
            with self.assertRaisesRegex(RigError, '(?i)(update|upgrade|flash)'):
                rig.calibrate_encoder()
            self.assertFalse(any(c[1] == 'CALIBRATE' for c in self.fw.commands))
            self.assertIsNone(rig.error)

    def test_running_executor_rejected_before_calibration_write(self):
        with self.rig() as rig:
            rig.start('manual', .5)
            with self.assertRaises(RigError):
                rig.calibrate_encoder()
            self.assertFalse(any(c[1] == 'CALIBRATE' for c in self.fw.commands))

    def test_board_calibrating_flag_rejects_locally(self):
        self.fw.flags |= 256
        with self.rig() as rig:
            with self.assertRaisesRegex(RigError, '(?i)calibrat'):
                rig.calibrate_encoder()
            self.assertFalse(any(c[1] == 'CALIBRATE' for c in self.fw.commands))

    def test_motion_and_second_capture_rejected_while_calibration_waits(self):
        self.fw.delay = .25
        with self.rig() as rig, ThreadPoolExecutor(1) as pool:
            result = pool.submit(rig.calibrate_encoder)
            self.assertTrue(self.fw.started.wait(.5))
            for operation in (lambda: rig.start('manual', .2), rig.home, rig.calibrate_encoder):
                with self.assertRaisesRegex(RigError, '(?i)calibrat'):
                    operation()
            result.result(timeout=1)
            self.assertEqual(sum(c[1] == 'CALIBRATE' for c in self.fw.commands), 1)
            self.assertFalse(any(c[1] in ('MODE', 'HOME') for c in self.fw.commands))

    def test_stop_cancels_pending_capture_without_waiting_for_deadline(self):
        self.fw.delay = None
        with self.rig() as rig, ThreadPoolExecutor(1) as pool:
            result = pool.submit(rig.calibrate_encoder)
            self.assertTrue(self.fw.started.wait(.5))
            started = time.monotonic()
            rig.stop()
            self.assertLess(time.monotonic() - started, .5)
            with self.assertRaisesRegex(RigError, '(?i)cancel'):
                result.result(timeout=.5)
            self.assertFalse(self.fw.pending)
            self.assertFalse(self.fw.completed)

    def test_missing_ack_times_out_and_sends_stop(self):
        self.fw.delay = None
        with self.rig(rig_type=FastDeadlineRig) as rig:
            with self.assertRaisesRegex(RigError, 'CALIBRATE acknowledgement timeout'):
                rig.calibrate_encoder()
            self.assertEqual(rig.calibration_timeout, 6.)
            self.wait_until(lambda: not self.fw.pending)
            self.assertTrue(any(c[1] == 'STOP' for c in self.fw.commands))
            self.assertIsNotNone(rig.error)

    def test_failed_capture_sends_stop_and_never_reports_success(self):
        for failure in ('calibration_timeout', 'encoder', 'save'):
            with self.subTest(failure=failure):
                self.fw.failure = failure
                with self.rig() as rig:
                    with self.assertRaisesRegex(RigError, failure):
                        rig.calibrate_encoder()
                    self.wait_until(lambda: any(c[1] == 'STOP' for c in self.fw.commands))
                    self.assertFalse(self.fw.completed)
                    self.assertIsNotNone(rig.error)

    def test_ack_without_verified_saved_info_is_not_success(self):
        self.fw.saved = False
        with self.rig() as rig:
            with self.assertRaisesRegex(RigError, '(?i)sav'):
                rig.calibrate_encoder()
            self.wait_until(lambda: any(c[1] == 'STOP' for c in self.fw.commands))

    def test_keyboard_interrupt_after_write_cancels_calibration(self):
        self.fw.delay = None
        with self.rig(transport_factory=InterruptTransport) as rig:
            with self.assertRaises(KeyboardInterrupt):
                rig.calibrate_encoder()
            self.wait_until(lambda: self.fw.started.is_set() and not self.fw.pending)
            self.assertTrue(any(c[1] == 'STOP' for c in self.fw.commands))

    def test_console_prints_pose_before_wait_and_saved_reference_afterward(self):
        for pose, instruction in (('upright', 'straight up'), ('hanging', 'fully down')):
            with self.subTest(pose=pose), self.rig() as rig, ThreadPoolExecutor(1) as pool:
                output = io.StringIO()
                self.fw.started.clear()
                result = pool.submit(execute_command, rig, pose, output=output)
                self.assertTrue(self.fw.started.wait(.5))
                self.assertIn(instruction, output.getvalue())
                self.assertNotIn('saved', output.getvalue().lower())
                self.assertTrue(result.result(timeout=1))
                self.assertIn('saved', output.getvalue().lower())
                self.assertIn('3210', output.getvalue())

    def test_console_never_prompts_operator_to_hold_a_moving_pole(self):
        with self.rig() as rig:
            rig.start('manual', .5)
            output = io.StringIO()
            with self.assertRaises(RigError):
                execute_command(rig, 'upright', output=output)
            self.assertNotIn('hold the pole', output.getvalue())
            self.assertFalse(any(c[1] == 'CALIBRATE' for c in self.fw.commands))

    def test_noninteractive_calibration_command_waits_and_exits_stopped(self):
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            code = main(['--port', self.fw.port, '--command', 'hanging', '--log-dir', directory],
                        rig_factory=self.rig, output=output)
        self.assertEqual(code, 0)
        self.assertTrue(self.fw.completed)
        self.assertIn('3210', output.getvalue())
        self.assertFalse(self.fw.flags & 2)
