#!/usr/bin/env python3
"""Verify preserved source bytes and the latest frozen analysis; no hardware."""
import argparse
import ast
import gzip
import hashlib
import json
import shutil
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text())


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    xz = shutil.which('xz')
    if xz is None:
        raise RuntimeError('xz is needed to verify original archives')
    checked = []
    for relative in ('batch6/training', 'batch6/validation', 'batch7/training'):
        archive = ROOT / (relative + '-original.tar.xz')
        manifest = read(ROOT / (relative + '-original-manifest.json'))
        seen = set()
        with subprocess.Popen([xz, '-dc', str(archive)], stdout=subprocess.PIPE) as process:
            with tarfile.open(fileobj=process.stdout, mode='r|') as tar:
                for member in tar:
                    if member.isdir():
                        continue
                    assert member.isfile() and Path(member.name).name in manifest
                    name = Path(member.name).name
                    assert name not in seen
                    raw = tar.extractfile(member).read()
                    assert len(raw) == manifest[name]['bytes']
                    assert digest(raw) == manifest[name]['sha256'], member.name
                    seen.add(name)
                    checked.append(dict(archive=relative, member=member.name, sha256=digest(raw)))
            assert process.wait() == 0
        assert seen == set(manifest)
    freeze = read(ROOT / 'candidate-freeze-latest6.json')
    for name, expected in freeze['method_hashes'].items():
        assert digest((ROOT / 'tools' / name).read_bytes()) == expected, name
    fit_sources = {item['sha256'] for item in freeze['source_identities']}
    assert len(fit_sources) == 2 and freeze['training']['episodes'] == 19
    holdout = read(ROOT / 'analysis/batch7-latest6-check/summary.json')
    assert holdout['source_identity']['sha256'] not in freeze['development_source_sha256']
    assert holdout['freeze_sha256'] == digest((ROOT / 'candidate-freeze-latest6.json').read_bytes())
    assert len({row['short']['samples'] for row in holdout['results']}) == 1
    selected = next(row for row in holdout['results'] if row['model'] == 'weak_coulomb')
    assert selected['short_numeric_gates_pass'] and selected['short_coverage_gates_pass']
    assert holdout['accepted'] is False and holdout['model_exported'] is False
    assert holdout['camera_passed'] is False and holdout['poses_verified'] is False
    sim = read(ROOT / 'analysis/mujoco-batch7-hanging-zero/summary.json')
    previous_sim = read(ROOT / 'analysis/mujoco-batch7-latest6/summary.json')
    assert sim['measured_error'] == previous_sim['measured_error']
    assert sim['freeze_sha256'] == holdout['freeze_sha256']
    assert sim['ode_parity']['rms_deg'] < .1 and sim['ode_max_difference_deg'] < .3
    assert sim['force_equation_max_error_rad_s2'] < 1e-10
    assert sim['accepted'] is False
    failed_path = ROOT / 'analysis/batch7-failed-prefix-diagnostic/report.json.gz'
    failed = json.loads(gzip.decompress(failed_path.read_bytes()))
    assert failed['completion_report']['completed'] is False
    assert failed['collection_recovered'] is False and failed['accepted'] is False
    assert failed['raw_source_sha256'] not in freeze['development_source_sha256']
    assert failed['extract_sha256'] == digest((ROOT / 'batch7/failed-validation-diagnostic-extract.npz').read_bytes())
    for script in (ROOT / 'tools').glob('*.py'):
        ast.parse(script.read_text(), filename=str(script))
    output = dict(
        verified_original_files=checked,
        frozen_methods_unchanged=True,
        later_two_sources_only_in_latest_fit=True,
        completed_batch7_absent_from_fit_and_development_sources=True,
        short_comparisons_use_identical_sample_counts=True,
        display_zero_change_leaves_all_mujoco_scores_identical=True,
        mujoco_parity_checks_pass=True,
        original_measurement_and_collection_failures_preserved=True,
        all_tool_scripts_parse=True,
        production_model_exported=False,
    )
    args.output.write_text(json.dumps(output, indent=2) + '\n')
    print(json.dumps(dict(verified_original_files=len(checked), checks_passed=True), indent=2))


if __name__ == '__main__':
    main()
