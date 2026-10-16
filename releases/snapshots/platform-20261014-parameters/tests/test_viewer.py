"""Headless tests for the real SDK controller used by the native viewer."""
import importlib.util
import math
from pathlib import Path
import subprocess
import sys
import unittest

HAS_SIM = importlib.util.find_spec('mujoco') is not None
VIEWER = importlib.util.find_spec('cartpole_sdk.sim.viewer') if HAS_SIM else None
if VIEWER:
    from cartpole_sdk.sim.viewer import ViewerSession, copy_display_state
    from cartpole_sdk.sim import MujocoBackend, SensorConfig, SimulationConfig
    from cartpole_sdk.simulation import run_simulation
    from cartpole_sdk.control.policy import ReferencePolicy
    from cartpole_sdk import Channel, ValidationError
    import mujoco


@unittest.skipUnless(HAS_SIM, 'install the sim extra for viewer integration tests')
class ViewerAvailabilityTests(unittest.TestCase):
    def test_headless_controller_loop_exists(self):
        self.assertIsNotNone(VIEWER, 'viewer needs a headless SDK controller loop')


@unittest.skipUnless(VIEWER, 'viewer loop has not been implemented')
class ViewerSessionTests(unittest.TestCase):
    def make_session(self, **kwargs):
        backend = kwargs.pop('backend', None) or MujocoBackend(SimulationConfig(max_steps=100))
        self.addCleanup(backend.close)
        return ViewerSession(backend, **kwargs)

    def test_auto_starts_hanging_and_advances_real_one_ms_physics(self):
        session = self.make_session(seed=7)
        self.assertAlmostEqual(abs(session.backend.ground_truth.theta), math.pi)
        self.assertEqual(session.advance(20), 20)
        self.assertEqual(session.backend.observation.available_ns, 20_000_000)
        self.assertEqual(session.policy.last_output.mode, 2)
        self.assertNotEqual(session.backend.ground_truth.x, 0)

    def test_upright_ticks_match_sdk_runner_exactly(self):
        session = self.make_session(start_mode='upright', seed=9)
        session.advance(20)
        policy = ReferencePolicy(Channel('pole', 'angle', 'simulation', 'sim:upright+x'),
                                 Channel('cart', 'position', 'simulation', 'sim:upright+x'),
                                 start_mode='upright')
        run = run_simulation(policy, config=SimulationConfig(max_steps=20), seed=9,
                             state=(0., 0., .04, 0.))
        self.assertEqual(session.backend.ground_truth, run.steps[-1].truth)
        self.assertEqual(session.backend.observation, run.observations[-1])
        self.assertEqual(session.policy.last_output.acceleration,
                         run.steps[-1].action.acceleration_m_s2)

    def test_pause_and_explicit_reset_preserve_fixed_cadence(self):
        session = self.make_session(start_mode='upright')
        session.advance(12)
        session.paused = True
        before = session.backend.ground_truth
        self.assertEqual(session.advance(20), 0)
        self.assertEqual(session.backend.ground_truth, before)
        session.paused = False
        session.advance(3)
        self.assertIsNone(session.policy.fault_reason)
        session.reset()
        self.assertEqual(session.backend.observation.sequence, 0)
        self.assertEqual(session.advance(1), 1)
        self.assertIsNone(session.policy.fault_reason)

    def test_horizon_freezes_until_reset(self):
        session = self.make_session(backend=MujocoBackend(SimulationConfig(max_steps=3)))
        self.assertEqual(session.advance(20), 3)
        self.assertEqual(session.end_reason, 'horizon')
        before = session.backend.ground_truth
        self.assertEqual(session.advance(20), 0)
        self.assertEqual(session.backend.ground_truth, before)
        self.assertEqual(session.backend.data.qfrc_applied.tolist(), [0., 0.])
        session.reset()
        self.assertEqual(session.advance(1), 1)

    def test_policy_sensor_fault_latches_without_physics_step(self):
        session = self.make_session(backend=MujocoBackend(sensors=SensorConfig(delay_steps=1)))
        self.assertEqual(session.advance(20), 0)
        self.assertEqual(session.end_reason, 'policy_fault')
        self.assertTrue(session.fault_reason)
        self.assertEqual(session.backend.observation.sequence, 0)
        self.assertEqual(session.advance(20), 0)

    def test_rail_stop_freezes_until_explicit_reset(self):
        session = self.make_session(backend=MujocoBackend(SimulationConfig(rail_half_m=.01)),
                                    start_mode='upright', state=(.0099, 1., .04, 0.))
        self.assertEqual(session.advance(20), 1)
        self.assertEqual(session.end_reason, 'rail_limit')
        self.assertEqual(session.advance(1), 0)
        self.assertEqual(session.backend.data.qfrc_applied.tolist(), [0., 0.])

    def test_window_keys_are_queued_until_main_loop_applies_them(self):
        session = self.make_session(start_mode='upright')
        session.advance(2)
        session.key_callback(32)
        self.assertFalse(session.paused)
        session.apply_pending_commands()
        self.assertTrue(session.paused)
        session.key_callback(ord('R'))
        session.apply_pending_commands()
        self.assertFalse(session.paused)
        self.assertEqual(session.backend.observation.sequence, 0)
        session.key_callback(256)
        session.apply_pending_commands()
        self.assertTrue(session.exit_requested)

    def test_wrong_control_cadence_is_rejected(self):
        with self.assertRaisesRegex(ValidationError, '1 ms'):
            self.make_session(backend=MujocoBackend(SimulationConfig(control_steps=2)))

    def test_gui_reset_and_option_changes_cannot_reset_authoritative_backend(self):
        session = self.make_session(start_mode='upright')
        session.advance(20)
        truth = session.backend.ground_truth
        display_model = mujoco.MjModel.from_xml_string(session.backend.model_xml)
        display_data = mujoco.MjData(display_model)
        copy_display_state(session, display_model, display_data)
        self.assertEqual(display_data.time, session.backend.data.time)
        mujoco.mj_resetData(display_model, display_data)
        display_model.opt.timestep = .05
        copy_display_state(session, display_model, display_data)
        self.assertEqual(session.backend.ground_truth, truth)
        self.assertEqual(display_data.qpos.tolist(), session.backend.data.qpos.tolist())
        self.assertEqual(session.backend.model.opt.timestep, .001)
        self.assertEqual(session.advance(1), 1)
        self.assertIsNone(session.policy.fault_reason)

    def test_overlay_requests_never_hold_the_render_thread_mutex(self):
        # MuJoCo 3.15 set_texts can wait for the render thread to consume a
        # prior overlay. Holding its mutex during that wait deadlocks the GUI.
        from contextlib import contextmanager
        from unittest.mock import patch
        from cartpole_sdk.sim.viewer import run_viewer

        class Viewer:
            def __init__(self):
                self.cam = mujoco.MjvCamera()
                self.user_scn = mujoco.MjvScene(mujoco.MjModel.from_xml_string('<mujoco/>'), maxgeom=10)
                self.locked = False
                self.overlay_calls = 0
                self.frames = 0
            def __enter__(self): return self
            def __exit__(self, *_): pass
            @contextmanager
            def lock(self):
                self.locked = True
                try: yield
                finally: self.locked = False
            def set_texts(self, _):
                if self.locked:
                    raise AssertionError('overlay request blocks the render thread mutex')
                self.overlay_calls += 1
            def sync(self):
                if self.locked: raise AssertionError('sync under render mutex')
            def is_running(self):
                self.frames += 1
                return self.frames <= 2

        viewer = Viewer()
        with patch('mujoco.viewer.launch_passive', return_value=viewer):
            run_viewer()
        self.assertGreaterEqual(viewer.overlay_calls, 3)

    def test_example_help_does_not_start_window(self):
        example = Path(__file__).resolve().parents[1] / 'examples' / 'view_simulation.py'
        result = subprocess.run([sys.executable, str(example), '--help'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--start', result.stdout)
        self.assertIn('--duration', result.stdout)

    @unittest.skipUnless(sys.platform == 'darwin', 'macOS launcher restriction')
    def test_mac_ordinary_python_explains_required_launcher(self):
        example = Path(__file__).resolve().parents[1] / 'examples' / 'view_simulation.py'
        result = subprocess.run([sys.executable, str(example), '--duration', '.01'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('mjpython', result.stderr)
        self.assertNotIn('Traceback', result.stderr)

    def test_import_does_not_load_native_viewer(self):
        result = subprocess.run([sys.executable, '-c',
            'import sys; import cartpole_sdk.sim.viewer; '
            'assert "mujoco.viewer" not in sys.modules'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
