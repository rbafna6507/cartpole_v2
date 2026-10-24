"""Vertical wire and PTY lifecycle checks; never access physical devices."""
import io
import time
import unittest
from cartpole_sdk.contracts import ValidationError
from cartpole_sdk.rig import Rig, RigError
from cartpole_sdk.rig import protocol
from cartpole_sdk.rig.console import execute_command
from test_rig import Firmware, FDTransport

class VerticalFirmware(Firmware):
    def __init__(self):
        self.phase=0
        self.refs=3
        self.z_end=None
        self.height=25
        self.maximum=120
        self.legacy=False
        super().__init__()
    def command(self,payload):
        p=payload.split()
        if p[1]=='INFO':
            self.commands.append(p)
            self.send(f'V2 INFO {self.sid} executor-v7-vertical 270 1 32 0 1 14000 .35 768 768 1 2318 0 0')
        elif p[1]=='ZSTATUS':
            self.commands.append(p)
            self.send(f'V2 Z {self.sid} {self.phase} {self.refs} {self.height} {self.height} 0' + ('' if self.legacy else f' {self.maximum}'))
        elif p[1].startswith('Z'):
            self.commands.append(p)
            if p[1]=='ZLIMIT':self.maximum=float(p[3])
            if p[1] in ('ZMOVE','ZHOME','ZSINE'):
                self.phase=1; self.z_end=self.ticks()+60
                if self.mode==0:self.mode=15;self.flags|=2
                self.watchdog=self.ticks()+200
            if p[1]=='ZSTOP':
                self.phase=0;self.z_end=None
                if self.mode==15:self.mode=0;self.flags&=~2
            self.send(f'V2 OK {self.sid} {p[1]}');self.send(self.state())
        else:super().command(payload)
    def state(self,**kwargs):
        if self.z_end is not None and self.ticks()>=self.z_end:
            self.phase=0;self.z_end=None
            if self.mode==15:self.mode=0;self.flags&=~2
        return super().state(**kwargs)

class VerticalTests(unittest.TestCase):
    def rig(self):
        fw=VerticalFirmware();self.addCleanup(fw.close)
        return fw,Rig(fw.port,transport_factory=FDTransport,command_timeout=.2)
    def wait(self,predicate):
        deadline=time.monotonic()+.8
        while not predicate():
            if time.monotonic()>deadline:self.fail('condition timeout')
            time.sleep(.003)
    def test_metadata_strict(self):
        self.assertTrue(hasattr(protocol,'parse_z_status'))
        parse=protocol.parse_z_status
        z=parse('V2 Z 1 4 3 25.5 24 0',received_ns=123)
        self.assertEqual((z.phase,z.refs,z.left_mm,z.right_mm,z.bottom_mask),(4,3,25.5,24,0))
        for bad in ('V2 Z 1 4 3 25 24','V2 Z 0 0 0 0 0 0','V2 Z 1 5 0 0 0 0','V2 Z 1 0 4 0 0 0','V2 Z 1 0 0 nan 0 0','V2 Z 1 0 0 1_0 0 0','V2 Z 1 0 0 0 0 4'):
            with self.subTest(bad=bad),self.assertRaises(protocol.ProtocolError):parse(bad,received_ns=1)
    def test_standalone_move_completes_and_logs(self):
        fw,rig=self.rig()
        with rig:
            z=rig.z_status();self.assertEqual(z.refs,3)
            rig.z_move('left',2)
            self.assertTrue(rig._z_active)
            self.wait(lambda:not rig._z_active)
            self.assertIsNone(rig.error)
            self.assertFalse(rig.state.enabled)
            self.assertTrue(any(r['type']=='z_status' for r in rig.records))
    def test_cart_authority_survives_z_stop(self):
        fw,rig=self.rig()
        with rig:
            rig.start('auto',5)
            deadline=rig._deadline_ns
            rig.z_move('both',2)
            rig.z_stop()
            self.assertEqual(rig._deadline_ns,deadline)
            self.assertTrue(rig._active)
            self.assertTrue(rig._return_expected)
            self.assertEqual(rig.state.mode,2)
    def test_stale_standalone_stops(self):
        fw,rig=self.rig()
        with rig:
            rig.z_home('both');fw.z_end=None;fw.quiet=True
            self.wait(lambda:rig.error is not None)
            self.assertIn('stale',str(rig.error))
    def test_deadline_stops_standalone(self):
        fw,rig=self.rig()
        with rig:
            rig.z_home('left');fw.z_end=None
            rig._z_deadline_ns=time.monotonic_ns()
            self.wait(lambda:rig.error is not None)
            self.assertIn('vertical',str(rig.error))
    def test_console_and_validation(self):
        fw,rig=self.rig()
        with rig:
            output=io.StringIO()
            for cmd in ('z status','z reference both','z move left down 2','z stop','z home right','z stop','z sine','z stop'):
                execute_command(rig,cmd,output=output)
            move=next(p for p in fw.commands if p[1]=='ZMOVE')
            self.assertEqual(float(move[4]),-2)
            self.assertEqual(float(move[5]),2)
            for cmd in ('z move left down -2','z move both up 21','z move both up nan','z move left up 1 41','z move bogus up 1','z sine 1 2','z status extra'):
                with self.subTest(cmd=cmd),self.assertRaises((ValidationError,ValueError)):execute_command(rig,cmd,output=output)
    def test_legacy_rejected_without_latching(self):
        fw=Firmware();self.addCleanup(fw.close)
        with Rig(fw.port,transport_factory=FDTransport) as rig:
            with self.assertRaisesRegex(RigError,'vertical'):rig.z_home('both')
            self.assertIsNone(rig.error)
            self.assertFalse(any(p[1].startswith('Z') for p in fw.commands))
    def test_balance_prefetches_capability(self):
        fw,rig=self.rig()
        with rig:
            rig.start('bal',5)
            rig.z_move('both',2)
            self.assertEqual(rig.state.mode,3)
            self.assertIsNone(rig.error)
    def test_fault_status_and_z_stop_remain_available(self):
        fw,rig=self.rig()
        with rig:
            rig.z_status()
            rig._latch(RigError('test fault'))
            self.assertEqual(rig.z_status().refs,3)
            self.assertEqual(rig.z_stop().phase,0)
            self.assertIsNotNone(rig.error)
    def test_missing_reference_and_endpoints_refuse_before_command(self):
        fw,rig=self.rig()
        with rig:
            fw.refs=1
            with self.assertRaisesRegex(RigError,'reference'):rig.z_move('right',2)
            with self.assertRaisesRegex(RigError,'references'):rig.z_sine()
            for kwargs in ({'hz':float('nan')},{'hz':6},{'seconds':3},{'amplitude_mm':100},{'center_mm':2}):
                with self.assertRaises(ValidationError):rig.z_sine(**kwargs)
            self.assertFalse(any(p[1] in ('ZMOVE','ZSINE') for p in fw.commands))
    def test_move_duration_is_bounded(self):
        fw,rig=self.rig()
        with rig:
            with self.assertRaisesRegex(ValidationError,'60s'):rig.z_move('both',20,.001)
            self.assertFalse(any(p[1]=='ZMOVE' for p in fw.commands))

    def test_default_ceiling_blocks_move_and_sine(self):
        fw,rig=self.rig()
        with rig:
            fw.height=120
            with self.assertRaises(ValidationError):rig.z_move('both',1)
            with self.assertRaises(ValidationError):rig.z_sine(20,1,100,10)
            self.assertFalse(any(p[1] in ('ZMOVE','ZSINE') for p in fw.commands))
    def test_custom_ceiling_command_and_metadata(self):
        fw,rig=self.rig()
        with rig:
            output=io.StringIO();execute_command(rig,'z limit',output=output)
            self.assertIn('120',output.getvalue())
            self.assertEqual(rig.z_status().max_mm,120)
            execute_command(rig,'z limit 100',output=output)
            self.assertTrue(any(p[1]=='ZLIMIT' and p[3]=='100' for p in fw.commands))
            for v in (0,9,201,float('nan'),float('inf')):
                with self.assertRaises(ValidationError):rig.z_limit(v)
            with self.assertRaises(ValidationError):rig.z_limit(20)

    def test_legacy_uses_host_ceiling_and_requires_flash_to_change(self):
        fw,rig=self.rig();fw.legacy=True
        with rig:
            self.assertIsNone(rig.z_status().max_mm)
            fw.height=120
            with self.assertRaises(ValidationError):rig.z_move('left',1)
            with self.assertRaisesRegex(RigError,'flash'):rig.z_limit(130)
            self.assertFalse(any(p[1] in ('ZMOVE','ZLIMIT') for p in fw.commands))
    def test_custom_limit_controls_later_moves(self):
        fw,rig=self.rig()
        with rig:
            rig.z_limit(30)
            with self.assertRaises(ValidationError):rig.z_move('both',6)
            with self.assertRaises(ValidationError):rig.z_sine()
            self.assertEqual(rig.z_limit().max_mm,30)
    def test_limit_metadata_rejects_invalid_values(self):
        for v in ('nan','inf','0','9','201','1_20'):
            with self.subTest(v=v),self.assertRaises(protocol.ProtocolError):
                protocol.parse_z_status('V2 Z 1 0 3 0 0 0 '+v,received_ns=1)
