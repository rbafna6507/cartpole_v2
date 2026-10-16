"""Default console tuning is tested through the real serial protocol over a PTY."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from cartpole_sdk.rig import Rig
from cartpole_sdk.rig.console import main
from test_rig import FDTransport
from test_rig_parameters import ParameterFirmware

class ConsoleStartupTests(unittest.TestCase):
    def setUp(self):
        self.fw=ParameterFirmware();self.addCleanup(self.fw.close)
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
    def rig(self,port,**kwargs):
        return Rig(port,transport_factory=FDTransport,command_timeout=.3,**kwargs)
    def run_console(self,extra=(),lines=('quit',)):
        output=io.StringIO();inputs=iter(lines)
        code=main(['--port',self.fw.port,'--log-dir',self.tmp.name,'--no-vision-telemetry',*extra],rig_factory=self.rig,input_fn=lambda _:next(inputs),output=output)
        return code,output.getvalue()
    def test_default_profile_applied_before_prompt_without_motion_or_recalibration(self):
        self.fw.values.update(pw=6,bw=30,ke=7,rail=.11)
        seen=[]
        def first_prompt(_):
            seen.append(dict(self.fw.values));return 'quit'
        out=io.StringIO()
        code=main(['--port',self.fw.port,'--log-dir',self.tmp.name,'--no-vision-telemetry'],rig_factory=self.rig,input_fn=first_prompt,output=out)
        self.assertEqual(code,0,out.getvalue());self.assertEqual(seen[0]['bw'],10)
        self.assertEqual(seen[0]['pw'],3);self.assertEqual(seen[0]['ke'],4)
        self.assertEqual(seen[0]['jmax'],150);self.assertEqual(seen[0]['rail'],.11)
        self.assertFalse(any(c[1] in ('ARM','MODE','HOME','CENTER','CAL') for c in self.fw.commands))
        self.assertIn('tuned-20261016-bw10',out.getvalue());self.assertFalse(self.fw.flags&2)
    def test_keep_board_parameters_skips_default_load(self):
        self.fw.values.update(pw=5.5,bw=12)
        code,out=self.run_console(['--keep-board-params'])
        self.assertEqual(code,0,out);self.assertFalse(self.fw.writes)
        self.assertEqual(self.fw.values['pw'],5.5)
    def test_custom_startup_profile_replaces_default(self):
        p=Path(self.tmp.name)/'experiment.json';p.write_text(json.dumps({'schema_version':1,'parameters':{'bw':7,'pw':2.75}}))
        self.fw.values['ke']=6
        code,out=self.run_console(['--startup-profile',str(p)])
        self.assertEqual(code,0,out);self.assertEqual(self.fw.values['bw'],7)
        self.assertEqual(self.fw.values['pw'],2.75);self.assertEqual(self.fw.values['ke'],6)
    def test_read_only_cli_commands_preserve_live_parameters(self):
        for command in ('info','status','params'):
            with self.subTest(command=command):
                code,out=self.run_console(['--command',command])
                self.assertEqual(code,0,out);self.assertFalse(self.fw.writes)
    def test_bad_explicit_profile_fails_before_opening_serial(self):
        p=Path(self.tmp.name)/'bad.json';p.write_text('{"schema_version":1,"parameters":{"bw":-1}}')
        code,out=self.run_console(['--startup-profile',str(p)])
        self.assertEqual(code,1,out);self.assertFalse(self.fw.commands)
    def test_rejected_default_load_cannot_start_queued_motion(self):
        self.fw.reject='bw'
        code,out=self.run_console(lines=('auto 1','quit'))
        self.assertEqual(code,1,out)
        self.assertFalse(any(c[1] in ('ARM','MODE') for c in self.fw.commands))
        self.assertFalse(self.fw.flags&2)
    def test_faulted_console_stays_available_then_loads_after_clear(self):
        self.fw.fault=4;self.fw.mode=4
        observed=[];lines=iter(('status','clear','quit'))
        def input_fn(_):
            line=next(lines);observed.append((line,dict(self.fw.values),list(self.fw.writes)));return line
        out=io.StringIO();code=main(['--port',self.fw.port,'--log-dir',self.tmp.name,'--no-vision-telemetry'],rig_factory=self.rig,input_fn=input_fn,output=out)
        self.assertEqual(code,0,out.getvalue());self.assertFalse(observed[0][2])
        self.assertEqual(observed[-1][1]['bw'],10);self.assertEqual(observed[-1][1]['pw'],3)
        self.assertFalse(any(c[1] in ('ARM','MODE') for c in self.fw.commands))
    def test_operator_edits_are_not_reset_between_commands(self):
        code,out=self.run_console(lines=('set bw 7','get bw','quit'))
        self.assertEqual(code,0,out);self.assertEqual(self.fw.values['bw'],7)

    def test_noninteractive_balance_loads_before_enabling(self):
        code,out=self.run_console(['--command','bal','--duration','.05'])
        self.assertEqual(code,0,out);self.assertEqual(self.fw.values['bw'],10)
        mode=next(i for i,c in enumerate(self.fw.commands) if c[1]=='MODE')
        self.assertTrue(any(c[1]=='PARAM' and c[3]=='bw' for c in self.fw.commands[:mode]))
        self.assertFalse(self.fw.flags&2)

    def test_unsupported_firmware_rejects_default_before_parameter_requests(self):
        from test_rig import Firmware
        old=Firmware();self.addCleanup(old.close);out=io.StringIO()
        code=main(['--port',old.port,'--log-dir',self.tmp.name,'--no-vision-telemetry'],rig_factory=self.rig,input_fn=lambda _: 'quit',output=out)
        self.assertEqual(code,1,out.getvalue())
        self.assertFalse(any(c[1]=='PARAM' for c in old.commands))
        self.assertIn('--keep-board-params',out.getvalue())
