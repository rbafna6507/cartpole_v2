"""V4 return-to-center lifecycle over a real PTY; no physical devices."""
import io
import tempfile
import time
import unittest
from cartpole_sdk.rig import Rig, RigError
from cartpole_sdk.rig.console import execute_command, main, _wait_run, _wait_home
from cartpole_sdk.rig.protocol import parse_info, parse_state, ProtocolError
from test_rig import Firmware, FDTransport
from test_rig_calibration import CalibrationFirmware

class ReturnFirmware(Firmware):
    def __init__(self, identity='executor-v4-rehome'):
        self.identity=identity
        self.auto_end=None
        self.return_end=None
        self.return_ms=60
        self.return_completed=0
        self.cancelled_return=0
        self.stall_return=False
        self.status_delay_ms=0
        self.stale_idle_status_once=False
        super().__init__()
    def command(self, payload):
        p=payload.split()
        if p[1]=='STATUS' and self.flags&2 and self.stale_idle_status_once:
            self.stale_idle_status_once=False
            self.commands.append(p)
            parts=super().state().split();parts[5]='0';parts[6]='5';parts[10]='0'
            self.send(' '.join(parts));return
        if p[1]=='STATUS' and self.flags&2 and self.status_delay_ms:
            time.sleep(self.status_delay_ms/1000)
        if p[1]=='INFO':
            self.commands.append(p)
            extra=' 768 768 1 2318 0 0' if self.identity in ('executor-v3-encguard','executor-v4-rehome','executor-v5-calmodel') else ''
            self.send(f'V2 INFO {self.sid} {self.identity} 270 1 32 0 1 14000 0.26'+extra)
            return
        if p[1]=='REHOME':
            self.commands.append(p)
            self.mode=14;self.flags|=2;self.expiry=None
            self.return_end=self.ticks()+self.return_ms
            self.duration=self.ticks()+15000;self.watchdog=self.ticks()+200
            self.send(f'V2 OK {self.sid} REHOME');self.send(self.state())
            return
        if p[1]=='STOP':
            if self.mode==14:self.cancelled_return+=1
            self.auto_end=self.return_end=None
        super().command(payload)
        if p[1]=='MODE' and p[3]=='auto' and self.identity in ('executor-v4-rehome','executor-v5-calmodel'):
            self.auto_end=self.ticks()+int(p[-1]);self.duration=None
    def state(self, **kwargs):
        now=self.ticks()
        if self.auto_end is not None and now>=self.auto_end and self.flags&2:
            self.mode=14;self.auto_end=None;self.return_end=now+self.return_ms
        if self.mode==14 and not self.stall_return and now>=self.return_end:
            self.mode=0;self.flags&=~2;self.return_end=None;self.return_completed+=1
        parts=super().state(**kwargs).split()
        if self.mode==0 and self.return_completed:parts[10]='0'
        return ' '.join(parts)

class ReturnTests(unittest.TestCase):
    def setUp(self):
        self.fw=ReturnFirmware()
        self.addCleanup(self.fw.close)
    def rig(self, port=None, **kwargs):
        return Rig(port or self.fw.port,transport_factory=FDTransport,command_timeout=.15,**kwargs)
    def wait(self, predicate, timeout=.5):
        end=time.monotonic()+timeout
        while not predicate():
            if time.monotonic()>=end:self.fail('return lifecycle timed out')
            time.sleep(.002)
    def test_v4_info_layout_and_return_mode_are_explicit(self):
        info=parse_info('V2 INFO 7 executor-v4-rehome 270 1 32 0 1 14000 0.26 768 768 1 2318 0 0',received_ns=1)
        self.assertEqual(info.firmware,'executor-v4-rehome')
        state=parse_state('V2 S 7 1 1000 14 7 0 0 0 .1 0 0 0 0 0 0 0 0',received_ns=1)
        self.assertEqual(state.mode,14)
        with self.assertRaises(ProtocolError):
            parse_state('V2 S 7 1 1000 15 7 0 0 0 .1 0 0 0 0 0 0 0 0',received_ns=1)
    def test_explicit_rehome_preserves_reference_and_finishes_disabled(self):
        with self.rig() as rig:
            rig.rehome()
            self.assertEqual(rig.state.mode,14)
            self.wait(lambda:self.fw.return_completed==1)
            self.wait(lambda:not rig._active)
            self.assertTrue(rig.state.homed)
            self.assertFalse(rig.state.enabled)
            self.assertIsNone(rig.error)
            self.assertFalse(any(c[1] in ('HOME','CENTER','CLEAR','MODE') for c in self.fw.commands))
    def test_rehome_refuses_legacy_unhomed_unhealthy_active_and_rate_zero(self):
        for change in ('legacy','unhomed','unhealthy','active','rate_zero'):
            with self.subTest(change=change):
                self.fw.identity='executor-v3-encguard' if change=='legacy' else 'executor-v4-rehome'
                self.fw.flags=1 if change=='unhomed' else (4 if change=='unhealthy' else 5)
                with self.rig(rate_hz=0 if change=='rate_zero' else 100) as rig:
                    if change=='active':rig.start('manual',.4)
                    with self.assertRaises(RigError):rig.rehome()
                self.assertFalse(any(c[1]=='REHOME' for c in self.fw.commands))
                self.fw.commands.clear();self.fw.fault=0;self.fw.mode=0
    def test_interactive_auto_keeps_heartbeat_through_duration_and_return(self):
        with self.rig(heartbeat_interval=.01) as rig:
            execute_command(rig,'auto .04',output=io.StringIO())
            self.wait(lambda:self.fw.return_completed==1)
            self.wait(lambda:not rig._active)
            self.assertEqual(self.fw.cancelled_return,0)
            self.assertIsNone(rig.error)
            self.assertFalse(any(c[1]=='STOP' for c in self.fw.commands))
    def test_v4_budget_is_extended_only_for_auto_not_bal_or_manual(self):
        with self.rig() as rig:
            for mode in ('auto','bal','manual'):
                start=time.monotonic_ns();rig.start(mode,.2)
                remaining=(rig._deadline_ns-start)/1e9
                if mode=='auto':self.assertTrue(15.2<=remaining<15.8)
                else:self.assertTrue(.19<=remaining<.3)
                rig.stop()
    def test_legacy_auto_keeps_early_stopping_budget(self):
        import math
        from dataclasses import replace
        from types import SimpleNamespace
        from unittest.mock import patch
        from test_rig_console import ScriptedClock, ScriptedConsoleRig

        class BudgetRig(ScriptedConsoleRig):
            def _command_state(self, command, *args, **kwargs):
                super()._command_state(command, *args, **kwargs)
                if command=='MODE':
                    # Native AUTO has the run-duration deadline, not the
                    # scripted external controller's 20 ms action lease.
                    self._state=replace(self._state, mode=2)
                    self._lease_until_ns=self.clock.now_ns+int(args[-1])*1_000_000

            def wait_state(self, after_tick=None, timeout=1):
                # The wait may end before the next 10 ms telemetry publication,
                # including a sub-nanosecond remainder from float arithmetic.
                if timeout<.01:
                    self.clock.now_ns+=max(1,math.ceil(timeout*1e9))
                    raise TimeoutError('no snapshot before deadline')
                return super().wait_state(after_tick,timeout)

        # This tests deadline arithmetic, not whether the host scheduler can
        # deliver STOP in a 10 ms window. PTY tests retain real expiry coverage.
        for identity in ('executor-v1','executor-v2-cart2','executor-v3-encguard'):
            clock=ScriptedClock()
            with self.subTest(identity=identity), \
                    patch('cartpole_sdk.rig.client.time', clock), \
                    patch('cartpole_sdk.rig.console.time', clock), \
                    BudgetRig('scripted-legacy', clock=clock) as rig:
                rig._info=SimpleNamespace(firmware=identity)
                rig.start('auto',.1)
                self.assertEqual(rig._deadline_ns,100_000_000)
                self.assertFalse(rig._return_expected)
                _wait_run(rig,.1,io.StringIO())
                self.assertTrue(90_000_000<=clock.now_ns<=90_000_001)
                self.assertEqual([c[1] for c in rig.commands],['MODE','STOP'])
                self.assertEqual(rig.commands[0][3:],['auto','100'])
                self.assertFalse(rig.state.enabled)
                self.assertIsNone(rig.error)
    def test_stop_cancels_return_without_later_restart(self):
        with self.rig() as rig:
            rig.rehome();rig.stop()
            time.sleep(.1)
            self.assertFalse(self.fw.flags&2)
            self.assertEqual(self.fw.return_completed,0)
            self.assertEqual(self.fw.cancelled_return,1)
            self.assertIsNone(rig._deadline_ns)
    def test_return_fault_and_telemetry_loss_stop_and_latch(self):
        for failure in ('fault','telemetry'):
            with self.subTest(failure=failure),self.rig() as rig:
                self.fw.stall_return=True
                rig.rehome()
                if failure=='fault':self.fw.fault=7;self.fw.mode=4;self.fw.flags&=~2
                else:self.fw.quiet=True
                self.wait(lambda:rig.error is not None and not rig._active)
                self.wait(lambda:not self.fw.flags&2)
                self.assertFalse(rig._active)
            self.fw.quiet=False;self.fw.fault=0;self.fw.mode=0
    def test_return_host_deadline_is_finite_and_never_restarts(self):
        with self.rig() as rig:
            self.fw.stall_return=True;rig.rehome()
            rig._deadline_ns=time.monotonic_ns()+30_000_000
            self.wait(lambda:not self.fw.flags&2)
            self.assertEqual(self.fw.return_completed,0)
            self.assertEqual(len([c for c in self.fw.commands if c[1]=='REHOME']),1)
            self.assertIsNotNone(rig.error)
            self.assertIn('return',str(rig.error).lower())
    def test_cli_auto_waits_through_return_and_stops_in_finally(self):
        with tempfile.TemporaryDirectory() as directory:
            output=io.StringIO()
            code=main(['--port',self.fw.port,'--keep-board-params','--command','auto','--duration','.04','--log-dir',directory],rig_factory=self.rig,output=output)
        self.assertEqual(code,0,output.getvalue())
        self.assertEqual(self.fw.return_completed,1)
        self.assertEqual(self.fw.cancelled_return,0)
        self.assertFalse(self.fw.flags&2)
        self.assertIn('return',output.getvalue().lower())
    def test_cli_rehome_waits_and_timeout_stops(self):
        with tempfile.TemporaryDirectory() as directory:
            output=io.StringIO()
            code=main(['--port',self.fw.port,'--command','rehome','--log-dir',directory],rig_factory=self.rig,output=output)
            self.assertEqual(code,0,output.getvalue())
            self.assertEqual(self.fw.return_completed,1)
            self.fw.stall_return=True
            code=main(['--port',self.fw.port,'--command','rehome','--duration','.03','--log-dir',directory],rig_factory=self.rig,output=output)
            self.assertEqual(code,1)
            self.assertFalse(self.fw.flags&2)

    def test_stop_before_auto_expiry_cancels_future_return(self):
        with self.rig() as rig:
            rig.start('auto',.04);rig.stop();time.sleep(.13)
            self.assertEqual(self.fw.return_completed,0)
            self.assertFalse(rig.state.enabled)
            self.assertFalse(any(r['type']=='state' and r['state']['mode']==14 for r in rig.records))
    def test_quit_and_interrupt_cancel_return(self):
        for command in ('quit','interrupt'):
            with self.subTest(command=command),tempfile.TemporaryDirectory() as directory:
                def input_fn(prompt):
                    self.fw.stall_return=True
                    if not any(c[1]=='REHOME' for c in self.fw.commands):return 'rehome'
                    if command=='interrupt':raise KeyboardInterrupt()
                    return 'quit'
                code=main(['--port',self.fw.port,'--keep-board-params','--log-dir',directory],rig_factory=self.rig,input_fn=input_fn,output=io.StringIO())
                self.assertEqual(code,130 if command=='interrupt' else 0)
                self.assertFalse(self.fw.flags&2)
                self.assertEqual(self.fw.return_completed,0)
                self.fw.commands.clear()
    def test_status_identifies_counted_home_return(self):
        with self.rig() as rig:
            rig.rehome();output=io.StringIO()
            execute_command(rig,'status',output=output)
            self.assertIn('"returning_to_existing_home":true',output.getvalue())
    def test_v4_calibration_keeps_existing_verified_reference_contract(self):
        fw=CalibrationFirmware();self.addCleanup(fw.close);fw.identity='executor-v4-rehome'
        with Rig(fw.port,transport_factory=FDTransport,command_timeout=.2) as rig:
            info=rig.calibrate_encoder('hanging')
            self.assertEqual(info.encoder_upright_raw,3210)
            self.assertTrue(info.encoder_conf_valid)
            self.assertFalse(rig.state.enabled)

    def test_unsolicited_stop_away_from_center_is_not_successful_return(self):
        with self.rig() as rig:
            self.fw.stall_return=True;rig.rehome()
            self.fw.mode=0;self.fw.flags&=~2
            self.wait(lambda:rig.error is not None)
            self.assertIn('return',str(rig.error).lower())
            self.assertFalse(rig._active)

    def test_immediate_return_clears_host_guard_without_enabled_snapshot(self):
        with self.rig() as rig:
            self.fw.return_ms=0
            rig.rehome()
            self.assertEqual(self.fw.return_completed,1)
            self.assertFalse(rig.state.enabled)
            self.assertFalse(rig._active)
            self.assertIsNone(rig._deadline_ns)
            self.assertIsNone(rig.error)
    def test_tiny_auto_and_return_can_complete_between_state_publications(self):
        with self.rig() as rig:
            self.fw.return_ms=0;self.fw.publish_commands=False;self.fw.status_delay_ms=5
            rig.start('auto',.001)
            self.assertEqual(self.fw.return_completed,1)
            self.assertFalse(rig.state.enabled)
            self.assertFalse(rig._active)
            self.assertIsNone(rig._deadline_ns)
            _wait_run(rig,.001,io.StringIO())
            self.assertIsNone(rig.error)

    def test_pending_idle_after_ack_cannot_clear_a_running_auto_guard(self):
        with self.rig() as rig:
            self.fw.publish_commands=False;self.fw.stale_idle_status_once=True
            rig.start('auto',.3)
            self.assertTrue(rig._active)
            self.assertIsNotNone(rig._deadline_ns)
            self.assertTrue(rig.state.enabled)
            self.assertFalse(self.fw.return_completed)
