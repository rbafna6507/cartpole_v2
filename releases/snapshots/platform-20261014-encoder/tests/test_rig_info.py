"""Read-only firmware identity, calibration and homing diagnostics."""
from dataclasses import asdict
import unittest
from cartpole_sdk.rig import Rig, RigError
from cartpole_sdk.rig.protocol import ProtocolError, parse_info
from test_rig import Firmware, FDTransport

PAYLOAD = 'V2 INFO 7 executor-v1 3485 1 103 0 2 13867 0.255'
GUARD_PAYLOAD = 'V2 INFO 7 executor-v3-encguard 270 1 103 4 2 13867 0.255 65535 768 1 2318 105000 2'

class InfoFirmware(Firmware):
    def __init__(self, payload=PAYLOAD):
        self.payload = payload
        super().__init__()

    def command(self, payload):
        if payload.split()[1] == 'INFO':
            self.commands.append(payload.split())
            self.send(self.payload.replace('INFO 7 ',f'INFO {self.sid} '))
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

    def test_legacy_diagnostics_leave_encoder_guard_fields_unknown(self):
        for identity in ('executor-v1', 'executor-v2-cart2'):
            with self.subTest(identity=identity):
                info = parse_info(PAYLOAD.replace('executor-v1', identity), received_ns=123)
                for field in ('encoder_boot_conf', 'encoder_conf', 'encoder_conf_valid',
                              'encoder_raw', 'encoder_raw_age_us', 'encoder_recoveries'):
                    self.assertIsNone(getattr(info, field))

    def test_guard_diagnostics_preserve_config_and_raw_change_age(self):
        info = parse_info(GUARD_PAYLOAD, received_ns=456)
        self.assertEqual(info.firmware, 'executor-v3-encguard')
        self.assertEqual(info.encoder_upright_raw, 270)
        self.assertEqual(info.encoder_boot_conf, 65535)
        self.assertEqual(info.encoder_conf, 768)
        self.assertIs(info.encoder_conf_valid, True)
        self.assertEqual(info.encoder_raw, 2318)
        self.assertEqual(info.encoder_raw_age_us, 105000)
        self.assertEqual(info.encoder_recoveries, 2)
        self.assertEqual(info.received_ns, 456)

    def test_guard_diagnostics_accept_unknown_reads_and_unmasked_config_bits(self):
        for suffix, expected in (
            ('-1 -1 0 0 4294967295 4294967295', (-1, -1, False, 0, 4294967295, 4294967295)),
            ('0 65535 0 4095 0 0', (0, 65535, False, 4095, 0, 0)),
            ('-1 50160 1 1 1 1', (-1, 50160, True, 1, 1, 1)),
            ('768 768 0 2318 0 0', (768, 768, False, 2318, 0, 0)),
        ):
            with self.subTest(suffix=suffix):
                info = parse_info(' '.join(GUARD_PAYLOAD.split()[:11])+' '+suffix, received_ns=1)
                self.assertEqual((info.encoder_boot_conf, info.encoder_conf, info.encoder_conf_valid,
                                  info.encoder_raw, info.encoder_raw_age_us, info.encoder_recoveries), expected)

    def test_guard_diagnostic_ranges_and_config_claims_are_strict(self):
        bad = [GUARD_PAYLOAD+' extra', ' '.join(GUARD_PAYLOAD.split()[:-1])]
        bad.extend(GUARD_PAYLOAD.replace('executor-v3-encguard', identity)
                   for identity in ('executor-v1', 'executor-v2-cart2'))
        bad.append(PAYLOAD.replace('executor-v1', 'executor-v3-encguard'))
        for index, values in ((11, ['-2', '65536', '1.0', '+1', '-01']),
                              (12, ['-2', '65536', 'nan', '-1', '0', '769', '1024']),
                              (13, ['-1', '2', 'true']), (14, ['-1', '4096']),
                              (15, ['-1', '4294967296']), (16, ['-1', '4294967296'])):
            for value in values:
                parts = GUARD_PAYLOAD.split();parts[index] = value;bad.append(' '.join(parts))
        for payload in bad:
            with self.subTest(payload=payload), self.assertRaises(ProtocolError):
                parse_info(payload, received_ns=1)

    def test_get_info_records_guard_diagnostics_without_motion(self):
        fw = InfoFirmware(GUARD_PAYLOAD);self.addCleanup(fw.close)
        with Rig(fw.port, transport_factory=FDTransport, command_timeout=.2) as rig:
            info = rig.get_info()
            self.assertEqual(info.encoder_raw_age_us, 105000)
            self.assertIs(info.encoder_conf_valid, True)
            recorded = next(r['info'] for r in rig.records if r['type'] == 'info')
            self.assertEqual(recorded['encoder_raw'], 2318)
            self.assertEqual(recorded['encoder_recoveries'], 2)
            self.assertFalse(any(c[1] in ('ARM', 'MODE') for c in fw.commands))

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
