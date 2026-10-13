import csv
import json
import tempfile
import unittest
from pathlib import Path

from cartpole_deploy.recording import capture_run
from cartpole_deploy.types import Observation
from cartpole_deploy.config import RigConfig


class FakeRig:
    def __init__(self, fail_at=None):
        self.tick = 0
        self.enabled = False
        self.stopped = False
        self.fail_at = fail_at
        self.homed = False
    def read(self):
        self.tick += 1
        if self.tick == self.fail_at:
            raise RuntimeError('sensor disconnected')
        return Observation(self.tick*10000, 'ARMED' if self.enabled else 'DISARMED',
                           3.14, 0, 0, 0, 0, 2048, 1 | (4 if self.enabled else 0), 0, 1, 'none')
    def home(self, rail_half_m=.15): self.homed = True
    def arm(self, session=None): self.enabled = True
    def command(self, kind, value, ttl_ms=50): pass
    def stop(self): self.enabled = False; self.stopped = True
    def capabilities(self): return {'encoder': True, 'imu': False}


class RecordingTests(unittest.TestCase):
    def test_hardware_drive_needs_explicit_assertions(self):
        with tempfile.TemporaryDirectory() as d:
            r = FakeRig()
            with self.assertRaises(ValueError):
                capture_run(r, RigConfig(), Path(d)/'run', mode='drive', seconds=.02)
            self.assertFalse(r.homed)
            self.assertFalse(r.enabled)

    def test_failure_preserves_partial_data_and_stops_owned_motion(self):
        with tempfile.TemporaryDirectory() as d:
            r = FakeRig(fail_at=4)
            p = Path(d)/'run'
            with self.assertRaises(RuntimeError):
                capture_run(r, RigConfig(), p, mode='drive', seconds=.1,
                            execute=True, center_confirmed=True, secured_z=True)
            self.assertTrue(r.stopped)
            metadata = json.loads((p/'metadata.json').read_text())
            self.assertEqual(metadata['status'], 'failed')
            with (p/'samples.csv').open() as f:
                self.assertGreater(len(list(csv.DictReader(f))), 0)

    def test_passive_capture_never_arms_or_stops_other_controller(self):
        with tempfile.TemporaryDirectory() as d:
            r = FakeRig()
            capture_run(r, RigConfig(), Path(d)/'run', mode='noise', seconds=.02)
            self.assertFalse(r.enabled)
            self.assertFalse(r.stopped)
            self.assertFalse(r.homed)

    def test_no_overwrite_of_previous_capture(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileExistsError):
                capture_run(FakeRig(), RigConfig(), Path(d), mode='noise', seconds=.02)

    def test_unconfirmed_stop_is_not_reported_as_success(self):
        class StopFailure(FakeRig):
            def stop(self):
                raise RuntimeError('connection lost')
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'run'
            with self.assertRaisesRegex(RuntimeError, 'stop.*not confirmed'):
                capture_run(StopFailure(), RigConfig(), p, mode='drive', seconds=.02,
                            execute=True, center_confirmed=True, secured_z=True)
            metadata = json.loads((p/'metadata.json').read_text())
            self.assertEqual(metadata['status'], 'stop_unconfirmed')
            self.assertIn('connection lost', metadata['stop_error'])
