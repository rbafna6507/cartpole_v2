"""Console and trusted policy runner exercise the PTY rig rather than mocks."""
from contextlib import redirect_stdout, redirect_stderr
import io
import json
import tempfile
import unittest
from cartpole_sdk.contracts import Acceleration, Channel
from cartpole_sdk.rig import Rig
from cartpole_sdk.rig.console import main, execute_command
from cartpole_sdk.rig.policy import run_policy
from test_rig import Firmware, FDTransport

CHANNELS=(Channel('pole','angle','magnetic','encoder-zero'), Channel('cart','position','step','cart-step-home'))

class FailingPolicy:
    def reset(self, session): self.session=session
    def act(self, observation): raise ValueError('policy failed')

class BoundedPolicy:
    def reset(self, session): pass
    def act(self, observation): return Acceleration(.1)

class PolicyAndConsoleTests(unittest.TestCase):
    def setUp(self):self.fw=Firmware()
    def tearDown(self):self.fw.close()
    def rig(self, port=None, **kwargs):
        return Rig(port or self.fw.port,transport_factory=FDTransport,command_timeout=.2,**kwargs)
    def test_noninteractive_auto_records_and_stops_finally(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            code=main(['--port',self.fw.port,'--command','auto','--duration','.04','--switches','off','--center-confirmed','--log-dir',directory],rig_factory=self.rig)
            self.assertEqual(code,0)
            records=[json.loads(s) for p in __import__('pathlib').Path(directory).glob('*.jsonl') for s in p.read_text().splitlines()]
            self.assertTrue(any(r['type']=='command' and 'MODE' in r['payload'] for r in records))
            self.assertEqual(self.fw.mode,0)
            self.assertEqual([c for c in self.fw.commands if c[1]!='STATUS'][-1][1],'STOP')
    def test_interactive_operator_commands_use_board_reference(self):
        with self.rig() as rig:
            output=io.StringIO()
            execute_command(rig,'switches off',output=output)
            execute_command(rig,'center',output=output)
            execute_command(rig,'auto .2',output=output)
            self.assertIn('board reference',output.getvalue())
            execute_command(rig,'stop',output=output)
            self.assertFalse(execute_command(rig,'quit',output=output))
    def test_noninteractive_home_waits_for_physical_routine_completion(self):
        self.fw.home_complete_ms=50
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            code=main(['--port',self.fw.port,'--command','home','--switches','on','--duration','.3','--log-dir',directory],rig_factory=self.rig)
        self.assertEqual(code,0)
        self.assertGreaterEqual(self.fw.ticks()-self.fw.home_started,50)
        self.assertEqual(self.fw.mode,0)

    def test_status_decodes_installed_cart_and_unused_open_inputs(self):
        self.fw.flags=201
        with self.rig() as rig:
            output=io.StringIO()
            execute_command(rig,'status',output=output)
            data=json.loads(output.getvalue())
            self.assertEqual(data['switch_inputs'],{
                '1_left':'closed', '2_right':'closed', '3':'open', '4':'open'})
            self.assertTrue(data['switch_checking_enabled'])
            self.assertTrue(data['encoder_healthy'])
            self.assertFalse(data['homed'])
            self.assertFalse(data['drivers_enabled'])

    def test_policy_exception_stops_in_finally(self):
        with self.rig() as rig:
            with self.assertRaises(ValueError):
                run_policy(rig,lambda channels:FailingPolicy(),channels=CHANNELS,duration_s=.2)
            self.assertFalse(self.fw.flags&2)
            self.assertTrue(any(c[1]=='ARM' for c in self.fw.commands))
    def test_bounded_external_policy_records_requests_and_does_not_select_reference(self):
        with self.rig() as rig:
            run_policy(rig,lambda channels:BoundedPolicy(),channels=CHANNELS,duration_s=.045)
            self.assertTrue(any(c[1]=='A' for c in self.fw.commands))
            self.assertFalse(any(c[1]=='MODE' for c in self.fw.commands))
            self.assertFalse(self.fw.flags&2)
            self.assertTrue(any(r['type']=='action_request' for r in rig.records))
    def test_policy_source_selection_failure_stops_before_arm(self):
        with self.rig() as rig:
            with self.assertRaises(ValueError):
                run_policy(rig,lambda channels:BoundedPolicy(),channels=(Channel('pole','angle','vision','missing'),),duration_s=.2)
            self.assertFalse(any(c[1]=='ARM' for c in self.fw.commands))
    def test_cli_rejects_policy_without_explicit_sources_before_connect(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main(['--port',self.fw.port,'--command','policy-zero'])
        self.assertFalse(self.fw.commands)
    def test_policy_output_above_commissioning_bound_stops(self):
        class Excessive(BoundedPolicy):
            def act(self, observation): return Acceleration(1.)
        with self.rig() as rig:
            with self.assertRaises(ValueError):
                run_policy(rig,lambda channels:Excessive(),channels=CHANNELS,duration_s=.2)
            self.assertFalse(any(c[1]=='A' for c in self.fw.commands))
            self.assertFalse(self.fw.flags&2)
