"""Read-only firmware identity, calibration and homing diagnostics."""
from dataclasses import asdict
import unittest
from cartpole_sdk.rig import Rig, RigError
from cartpole_sdk.rig.protocol import ProtocolError, parse_info
from test_rig import Firmware, FDTransport

PAYLOAD = 'V2 INFO 7 executor-v1 3485 1 103 0 2 13867 0.255'

class InfoFirmware(Firmware):
    def command(self, payload):
        if payload.split()[1] == 'INFO':
            self.commands.append(payload.split())
            self.send(PAYLOAD.replace('INFO 7 ',f'INFO {self.sid} '))
        else: super().command(payload)

class RigInfoTests(unittest.TestCase):
    def test_parse_exact_identity_and_live_calibration(self):
        info=parse_info(PAYLOAD, received_ns=123)
        self.assertEqual(info.encoder_upright_raw,3485)
        self.assertTrue(info.reference_saved)
        self.assertEqual(info.measured_span_steps,13867)
        self.assertEqual(info.home_epoch,2)
        self.assertAlmostEqual(info.rail_half_m,.255)
        self.assertEqual(info.received_ns,123)

    def test_cart_only_firmware_identity_is_supported(self):
        info=parse_info(PAYLOAD.replace('executor-v1','executor-v2-cart2'),received_ns=123)
        self.assertEqual(info.firmware,'executor-v2-cart2')
        self.assertEqual(info.encoder_upright_raw,3485)

    def test_invalid_diagnostic_payloads_are_rejected(self):
        bad=[PAYLOAD+' extra', PAYLOAD.replace('INFO','S')]
        for index,values in ((2,['0','-1']), (3,['unknown']), (4,['4096','-1','nan']),
                             (5,['2','true']), (6,['256','-1']), (7,['-1']),
                             (8,['-1']), (9,['-1','16001']), (10,['nan','inf','0','.261'])):
            for value in values:
                parts=PAYLOAD.split();parts[index]=value;bad.append(' '.join(parts))
        for payload in bad:
            with self.subTest(payload=payload),self.assertRaises(ProtocolError):
                parse_info(payload,received_ns=1)

    def test_get_info_uses_actual_reply_without_arming(self):
        fw=InfoFirmware();self.addCleanup(fw.close)
        with Rig(fw.port,transport_factory=FDTransport,command_timeout=.2) as rig:
            info=rig.get_info()
            self.assertEqual(info.encoder_upright_raw,3485)
            self.assertEqual(info.sid,rig.state.sid)
            self.assertFalse(any(c[1] in ('ARM','MODE') for c in fw.commands))
            self.assertTrue(any(r['type']=='info' and r['info']['reference_saved'] for r in rig.records))
            fw.fault=4;fw.mode=4
            rig._latch(RigError('encoder fault'))
            self.assertEqual(rig.get_info().encoder_upright_raw,3485)

    def test_get_info_rejects_active_motion_locally(self):
        fw=InfoFirmware();self.addCleanup(fw.close)
        with Rig(fw.port,transport_factory=FDTransport,command_timeout=.2) as rig:
            rig.start('auto',.2)
            with self.assertRaises(RigError):rig.get_info()
            self.assertFalse(any(c[1]=='INFO' for c in fw.commands))
