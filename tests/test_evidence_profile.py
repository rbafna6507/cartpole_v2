"""Evidence refresh preserves physical scope and produces portable training inputs."""
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from cartpole_sdk.learning.model_experiment import build_experiment, digest, load_training_model

ROOT = Path(__file__).resolve().parents[1]
BASE = 'training/profiles/rl-encoder-20261020'
SNAPSHOT = 'evidence/swingup-resonance-20261021/stopped-readback.json'
ARTIFACTS = {'model.json', 'executor-parameters.json', 'observation-config.json',
             'prior-parameters.json', 'randomization.json', 'provenance.json'}


def read(root, name):
    return json.loads((root / name).read_text())


def build(repo, output, angle_source='raw'):
    from cartpole_sdk.learning.evidence_profile import build_evidence_training_bundle
    return build_evidence_training_bundle(repo, output, angle_source=angle_source)


@pytest.mark.parametrize('angle_source', ['raw', 'vision', 'fused'])
def test_generated_profile_loads_with_retained_physics_and_current_executor(tmp_path, angle_source):
    profile = tmp_path / angle_source
    manifest = build(ROOT, profile, angle_source)
    admitted = load_training_model(profile / 'model.json', development_only=True)
    exp = build_experiment(profile / 'model.json',
        executor_parameters=read(profile, 'executor-parameters.json'),
        observation_config=read(profile, 'observation-config.json'),
        prior_parameters=read(profile, 'prior-parameters.json'), development_only=True)
    old = read(ROOT / BASE, 'model.json')['simulation_config']
    current = read(ROOT, SNAPSHOT)['parameters']
    expected = dict(old, rail_half_m=0.309074998)
    assert exp['simulation_config'] == expected
    assert exp['executor_parameters'] == current
    assert exp['executor_parameters']['bw'] == 10.
    assert exp['executor_parameters']['jmax'] == 150.
    assert exp['prior_parameters']['effective_length_m'] == .123999998
    assert exp['prior_parameters']['max_acceleration_m_s2'] == 25.
    assert exp['prior_length_matches_model'] is False
    assert exp['ttl_ms'] == 20 and exp['rate_hz'] == 100
    assert admitted['model']['accepted_fit'] is False
    assert admitted['task_qualified'] is False and admitted['hardware_accepted'] is False
    obs = exp['observation_config']
    assert obs['angle_source'] == angle_source
    assert obs['angle_frame_id'] == ('encoder-zero' if angle_source == 'raw' else 'physical-upright')
    assert {name: obs[name] for name in ('encoder_bias_rad', 'encoder_sin_error_rad',
                                        'encoder_cos_error_rad')} == {
        'encoder_bias_rad': 0., 'encoder_sin_error_rad': 0., 'encoder_cos_error_rad': 0.}
    assert obs['telemetry_delay_steps'] == 3 and obs['command_delay_steps'] == 1
    recipe = read(profile, 'randomization.json')
    from cartpole_sdk.learning.training_recipe import validate_randomization
    assert validate_randomization(recipe) == recipe
    for name, degrees in [('encoder_bias_rad', 1.), ('encoder_sin_error_rad', 4.),
                          ('encoder_cos_error_rad', 5.)]:
        assert recipe['encoder'][name] == pytest.approx([-math.radians(degrees), math.radians(degrees)])
    assert ('camera' in recipe) == (angle_source != 'raw')
    assert manifest['schema'] == 'cartpole-evidence-training-bundle-v1'
    assert set(manifest['files_sha256']) == ARTIFACTS
    assert manifest['hardware_accepted'] is False
    assert set(p.name for p in profile.iterdir()) == ARTIFACTS | {'bundle.json'}
    with pytest.raises(ValueError, match='development-only'):
        load_training_model(profile / 'model.json')


def test_bundle_and_sources_are_pinned_and_reproduce_after_checkout_relocation(tmp_path):
    profile = tmp_path / 'first'
    manifest = build(ROOT, profile)
    content = dict(manifest)
    pin = content.pop('content_sha256')
    assert digest(content) == pin
    for name, pin in manifest['files_sha256'].items():
        assert hashlib.sha256((profile / name).read_bytes()).hexdigest() == pin
    provenance = read(profile, 'provenance.json')
    assert provenance['source_accepted'] is False
    assert provenance['encoder_calibration_accepted'] is False
    assert provenance['hardware_accepted'] is False
    assert provenance['nominal_encoder_correction_applied'] is False
    assert provenance['recorded_executor_state']['encoder_upright_raw'] == 533
    assert provenance['recorded_executor_state']['measured_span_steps'] == 16511
    assert provenance['physical_parameter_changes'] == {'rail_half_m': {'old': .309000015, 'new': .309074998}}
    assert SNAPSHOT in provenance['sources_sha256']
    assert BASE + '/model.json' in provenance['sources_sha256']
    relocated = tmp_path / 'relocated'
    for name, pin in provenance['sources_sha256'].items():
        path = Path(name)
        assert not path.is_absolute() and '..' not in path.parts
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == pin
        target = relocated / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    second = tmp_path / 'second'
    assert build(relocated, second) == manifest
    for path in profile.iterdir():
        assert path.read_bytes() == (second / path.name).read_bytes()


def test_output_is_never_overwritten(tmp_path):
    output = tmp_path / 'profile'
    build(ROOT, output)
    before = {p.name: p.read_bytes() for p in output.iterdir()}
    with pytest.raises(FileExistsError):
        build(ROOT, output)
    assert before == {p.name: p.read_bytes() for p in output.iterdir()}


@pytest.mark.parametrize('change', ['altered_source', 'missing_executor', 'moving_snapshot',
                                    'missing_reference', 'missing_span'])
def test_invalid_source_leaves_no_partial_output(tmp_path, change):
    first = tmp_path / 'first'
    build(ROOT, first)
    copied = tmp_path / 'repo'
    for name in read(first, 'provenance.json')['sources_sha256']:
        target = copied / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    if change == 'altered_source':
        source = copied / BASE / 'model.json'
        payload = json.loads(source.read_text())
        payload['simulation_config']['cart_mass_kg'] = .9
    else:
        source = copied / SNAPSHOT
        payload = json.loads(source.read_text())
        if change == 'missing_executor':
            payload['parameters'].pop('jmax')
        elif change == 'moving_snapshot':
            payload['state']['velocity'] = .1
        elif change == 'missing_reference':
            payload['info'].pop('encoder_upright_raw')
        else:
            payload['info'].pop('measured_span_steps')
    source.write_text(json.dumps(payload))
    output = tmp_path / 'invalid'
    with pytest.raises(ValueError):
        build(copied, output)
    assert not output.exists()


def test_invalid_modality_leaves_no_output(tmp_path):
    output = tmp_path / 'invalid'
    with pytest.raises(ValueError, match='angle_source'):
        build(ROOT, output, 'filtered')
    assert not output.exists()


def test_cli_builds_profile_and_reports_refused_overwrite(tmp_path):
    command = [sys.executable, str(ROOT / 'examples/prepare_rig_training.py'),
               '--output', str(tmp_path / 'cli'), '--angle-source', 'fused']
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['hardware_accepted'] is False
    assert read(tmp_path / 'cli', 'observation-config.json')['angle_source'] == 'fused'
    again = subprocess.run(command, capture_output=True, text=True)
    assert again.returncode == 2 and 'profile' in again.stderr
