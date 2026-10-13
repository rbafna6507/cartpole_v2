"""Reproduce the offline assessment from explicit baseline 12-column telemetry.

Run from repository root with PYTHONPATH=src. Input directories are supplied
explicitly and never fetched from a device. Acceleration is commanded; omega is
omitted because its filtered effective timestamp is not available.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from cartpole_sdk.adapters import CONSOLE_COLUMNS
from cartpole_sdk.identification import identify_pendulum
from cartpole_sdk.recording import strict_json_loads


def assess(input_dirs, output_dir):
    canonical = {}
    datasets = []
    for directory in input_dirs:
        path = directory / 'telemetry.json'
        values = strict_json_loads(path.read_text())
        if any(len(row) != len(CONSOLE_COLUMNS) for row in values):
            raise ValueError('explicit baseline firmware column count mismatch')
        records = [dict(zip(CONSOLE_COLUMNS, row)) for row in values]
        rows = [dict(t_s=r['t_ms'] * .001, theta_rad=r['theta'], cart_acceleration_m_s2=r['accel'], valid=True,
                     run_id=directory.name, calibration_id='preserved-eeprom-ref-3485', clock_id='baseline-board-ms',
                     source='magnetic', frame_id='preserved-encoder-zero', acceleration_kind='commanded') for r in records]
        canonical[directory.name] = rows
        canonical_file = output_dir / (directory.name + '-rows.jsonl')
        canonical_file.write_text(''.join(json.dumps(r, separators=(',', ':')) + '\n' for r in rows))
        times = np.array([r['t_ms'] * .001 for r in records])
        angle = np.unwrap([r['theta'] for r in records])
        accel = np.array([r['accel'] for r in records])
        initial_idle = []
        for r in records:
            if r['mode'] != 0: break
            initial_idle.append(r['theta'])
        offset = float(np.median(initial_idle)) - math.pi if initial_idle else None
        datasets.append(dict(run_id=directory.name, explicit_columns=list(CONSOLE_COLUMNS), input_file=str(path),
                             input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), canonical_file=str(canonical_file),
                             canonical_file_sha256=hashlib.sha256(canonical_file.read_bytes()).hexdigest(),
                             related_hashes={name:hashlib.sha256((directory / name).read_bytes()).hexdigest()
                                             for name in ('wire.jsonl', 'report.json') if (directory / name).exists()},
                             sample_count=len(records), duration_s=float(times[-1] - times[0]), max_gap_s=float(np.max(np.diff(times))),
                             mode_counts={str(int(m)):sum(r['mode'] == m for r in records) for m in sorted({r['mode'] for r in records})},
                             angle_unwrapped_span_rad=float(np.ptp(angle)), command_acceleration_std_m_s2=float(np.std(accel)),
                             command_acceleration_range_m_s2=[float(accel.min()),float(accel.max())],
                             commanded_nonzero_samples=int(np.count_nonzero(accel)),
                             step_cart_end_m=records[-1]['x'], step_cart_max_abs_m=max(abs(r['x']) for r in records),
                             initial_idle_theta_minus_pi_rad=offset,
                             omega_omitted_reason='filtered firmware omega effective timestamp is unknown',
                             valid_basis='parent reports healthy magnetic state; no independently calibrated angle/cart truth'))
    full = 'baseline-20261013T224303Z'
    comparisons = []
    for other in canonical:
        if other == full: continue
        report = identify_pendulum(canonical[full], canonical[other], source='magnetic', acceleration_kind='commanded',
                                   provenance={'datasets':datasets, 'physical_calibration_modified':False})
        comparisons.append(dict(training_run=full, validation_run=other, report=report.to_dict()))
    result = dict(kind='actual original-controller trajectory assessment; rejected candidates are not plant estimates',
                  generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), datasets=datasets,
                  comparisons=comparisons, accepted_physical_model=any(c['report']['accepted'] for c in comparisons),
                  calibration_preserved=True,
                  limitations=['Closed-loop original-controller trajectory is not independent open-loop persistent excitation',
                               'Hanging-equilibrium magnetic zero is approximately0.1–0.13rad from pi; no calibration altered',
                               'Acceleration is commanded; cart step counts do not independently measure travel, acceleration or slip',
                               'Vision angle and metric cart calibration unavailable; no independent cart truth',
                               'Filtered omega timing is unknown; used angle-only prediction initialization',
                               'OLS/profile uncertainty is conditional and cannot remove calibration/model/clock bias'])
    output = output_dir / 'fuller-physical-assessment.json'
    output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, action='append', required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    result = assess(args.input, args.output_dir)
    print(json.dumps({'accepted_physical_model':result['accepted_physical_model'],
                      'comparisons':[dict(training_run=c['training_run'], validation_run=c['validation_run'],
                                          accepted=c['report']['accepted'], reasons=c['report']['reasons'],
                                          parameters=c['report']['parameters'], training=c['report']['training'],
                                          validation_metrics=c['report']['validation']) for c in result['comparisons']]}, indent=2))
