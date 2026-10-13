import contextlib
import io
import json
from pathlib import Path

from cartpole_deploy.cli import main
from cartpole_deploy.config import RigConfig


def invoke(*args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        status = main(list(map(str, args)))
    return status, out.getvalue(), err.getvalue()


def test_cli_simulation_info_and_readonly_stream():
    code, out, err = invoke('info')
    assert code == 0, err
    assert json.loads(out)['state']['mode'] == 'DISARMED'
    code, out, err = invoke('stream', '--sensor', 'encoder', '--seconds', '.06', '--hz', '50')
    assert code == 0, err
    samples = list(map(json.loads, out.splitlines()))
    assert len(samples) == 3
    assert samples[-1]['time_us'] == 40000
    code, out, err = invoke('stream', '--sensor', 'imu')
    assert code == 2
    assert 'IMU is not implemented' in err


def test_complete_mujoco_capture_fit_holdout_export(tmp_path):
    for name, angle in [('train', 25), ('validation', 40)]:
        code, out, err = invoke('capture', 'decay', '--seconds', 6, '--angle-deg', angle,
                                '--output', tmp_path/name)
        assert code == 0, err
        assert json.loads((tmp_path/name/'metadata.json').read_text())['status'] == 'complete'
    fit_path = tmp_path/'fit.json'
    code, out, err = invoke('fit', tmp_path/'train/samples.csv', '--release-s', 0,
                            '--cart-clamped', '--output', fit_path)
    assert code == 0, err
    fit = json.loads(fit_path.read_text())
    assert abs(fit['effective_length_m'] - RigConfig().effective_length_m) < .001
    assert abs(fit['damping_per_s'] - RigConfig().damping_per_s) < .03
    validation_path = tmp_path/'validation.json'
    code, out, err = invoke('validate', tmp_path/'validation/samples.csv', '--fit', fit_path,
                            '--release-s', 0, '--cart-clamped', '--output', validation_path)
    assert code == 0, err
    assert json.loads(validation_path.read_text())['rmse_rad'] < .003
    config_path = tmp_path/'fitted.json'
    code, out, err = invoke('export', '--fit', fit_path, '--validation', validation_path,
                            '--output', config_path)
    assert code == 0, err
    assert RigConfig.load(config_path).provenance['status'] == 'provisional_with_validation_metrics'


def test_simulation_drive_capture_and_hardware_gates(tmp_path):
    code, out, err = invoke('capture', 'drive', '--seconds', 2, '--output', tmp_path/'drive')
    assert code == 0, err
    metadata = json.loads((tmp_path/'drive/metadata.json').read_text())
    assert metadata['status'] == 'complete'
    assert metadata['samples'] == 301  # Includes one centered settling second.
    # Fails before any network connection is opened.
    code, out, err = invoke('--backend', 'hardware', 'capture', 'drive', '--output', tmp_path/'bad')
    assert code == 2
    assert '--execute' in err
    assert not (tmp_path/'bad').exists()
