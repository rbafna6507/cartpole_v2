"""Model-validated calibration over PTY, including unsupported-board fail closed."""
import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from cartpole_sdk.contracts import ValidationError
from cartpole_sdk.rig import RigError
from cartpole_sdk.rig.console import execute_command, main
from cartpole_sdk.sensing.calibration import CalibrationPolicy, fit_calibration
from test_angle_calibration import dataset
import test_rig_calibration as calibration_tests
import test_rig_rehome as return_tests

IDENTITY = dict(hardware_id='rig-a', source_id='encoder-a', fixture_id='fixture-a',
                sensor_config_id='as5600-conf-768', counts_per_turn=4096, frame_id='pole-upright')

class ModelCalibrationTests(calibration_tests.RigCalibrationTests):
    def setUp(self):
        super().setUp()
        self.fw.identity='executor-v5-calmodel'
        self.model=fit_calibration(dataset()).approve(approved_by='synthetic-test', approved_at='2026-10-15T12:00:00Z')

    def test_model_command_transmits_exact_validated_offset(self):
        with self.rig() as rig:
            info=rig.calibrate_encoder('hanging', hanging_model=self.model, calibration_identity=IDENTITY)
            command=next(c for c in self.fw.commands if c[1]=='CALIBRATE')
            self.assertEqual(command[3:], ['hanging','113'])
            self.assertTrue(info.reference_saved)
            self.assertFalse(rig.state.enabled)

    def test_unapproved_or_wrong_identity_never_writes(self):
        with self.rig() as rig:
            for model,identity in ((fit_calibration(dataset()),IDENTITY),
                                   (self.model,dict(IDENTITY,fixture_id='changed')),
                                   (self.model,dict(IDENTITY,counts_per_turn=8192)),
                                   (object(),IDENTITY),(self.model,None)):
                with self.subTest(identity=identity),self.assertRaises(ValidationError):
                    rig.calibrate_encoder('hanging',hanging_model=model,calibration_identity=identity)
            self.assertFalse(any(c[1]=='CALIBRATE' for c in self.fw.commands))

    def test_model_never_used_for_upright_and_identity_requires_model(self):
        with self.rig() as rig:
            with self.assertRaises(ValidationError):
                rig.calibrate_encoder('upright',hanging_model=self.model,calibration_identity=IDENTITY)
            with self.assertRaises(ValidationError):
                rig.calibrate_encoder('hanging',calibration_identity=IDENTITY)
            self.assertFalse(any(c[1]=='CALIBRATE' for c in self.fw.commands))

    def test_old_board_has_no_model_fallback(self):
        self.fw.identity='executor-v4-rehome'
        with self.rig() as rig:
            with self.assertRaisesRegex(RigError,'v5'):
                rig.calibrate_encoder('hanging',hanging_model=self.model,calibration_identity=IDENTITY)
            self.assertFalse(any(c[1]=='CALIBRATE' for c in self.fw.commands))

    def test_rejected_extension_has_no_uncorrected_retry(self):
        self.fw.failure='calibration_timeout'
        with self.rig() as rig:
            with self.assertRaises(RigError):
                rig.calibrate_encoder('hanging',hanging_model=self.model,calibration_identity=IDENTITY)
            self.assertEqual(len([c for c in self.fw.commands if c[1]=='CALIBRATE']),1)

    def test_console_bare_hanging_preserves_reference(self):
        with self.rig() as rig:
            with self.assertRaisesRegex(ValidationError,'model|ideal'):
                execute_command(rig,'hanging',output=io.StringIO())
            self.assertFalse(any(c[1]=='CALIBRATE' for c in self.fw.commands))

    def test_console_and_noninteractive_model_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            model=Path(directory)/'model.json'; identity=Path(directory)/'identity.json'
            model.write_text(json.dumps(self.model.to_dict()));identity.write_text(json.dumps(IDENTITY))
            with self.rig() as rig:
                output=io.StringIO()
                execute_command(rig,f'hanging {model} {identity}',output=output)
                self.assertIn('113',output.getvalue())
                self.assertIn('saved',output.getvalue())
            output=io.StringIO()
            code=main(['--port',self.fw.port,'--command','hanging','--hanging-model',str(model),
                       '--calibration-identity',str(identity),'--log-dir',directory],rig_factory=self.rig,output=output)
            self.assertEqual(code,0,output.getvalue())

    def test_model_runtime_quality_stricter_than_firmware_never_writes(self):
        data=dataset()
        for pair in data['pairs']:
            for pose in ('upright','hanging'):
                pair[pose]['raw_counts']=[370 if pose=='upright' else 2305]*512
                pair[pose]['sample_period_s']=.002
        for parameters in ({'min_window_samples':402},{'min_window_duration_s':.5},
                           {'max_window_span_counts':3},{'max_window_drift_counts':1}):
            model=fit_calibration(data,CalibrationPolicy(**parameters)).approve(
                approved_by='synthetic-test',approved_at='2026-10-15T12:00:00Z')
            with self.subTest(parameters=parameters),self.rig() as rig:
                with self.assertRaisesRegex(ValidationError,'capture|quality'):
                    rig.calibrate_encoder('hanging',hanging_model=model,calibration_identity=IDENTITY)
                self.assertFalse(any(c[1]=='CALIBRATE' for c in self.fw.commands))

class V5ReturnTests(return_tests.ReturnTests):
    def setUp(self):
        super().setUp()
        self.fw.identity='executor-v5-calmodel'
