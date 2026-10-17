#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=1.26,<3"]
# ///
"""Batch short completed pulse recordings without joining their physical clocks.

Repeat --training and --validation. The output contains canonical rows, source
and completion-report hashes, each analysis-time shift and the unchanged SDK
fitter report. No device access, model installation or calibration is performed.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src'))

# Fixed separator affects only display/analysis time. Identity changes and the
# retained invalid rows also split the existing fitter's integration windows.
INTER_RUN_GAP_S = 1.0


def digest(value):
    from cartpole_sdk.identification.workflow import digest as canonical_digest
    return canonical_digest(value)


def prepare_batch(training, validation):
    """Admit independent completed inputs and preserve every adapted row."""
    from cartpole_sdk.identification.rig_logs import rig_log_rows
    from cartpole_sdk.identification.workflow import load_records

    groups = {'training': list(training), 'validation': list(validation)}
    if not all(groups.values()):
        raise ValueError('at least one independent training and validation log required')
    seen_hashes, seen_sessions, seen_clocks, seen_measurements = set(), set(), set(), set()
    result = {}
    for role, specs in groups.items():
        prepared, inputs, start = [], [], 0.0
        for spec in specs:
            records, identity = load_records(spec)
            if identity.get('collection_report', {}).get('completed') is not True:
                raise ValueError('batch input requires its bound successful collection report')
            source_hash = identity['sha256']
            if source_hash in seen_hashes:
                raise ValueError('duplicate source content within or across training/validation')
            rows, admission = rig_log_rows(records, run_id=source_hash)
            if admission['session_id'] in seen_sessions or admission['clock_id'] in seen_clocks:
                raise ValueError('source session/clock overlap; independent recordings required')
            original_start, original_end = rows[0]['t_s'], rows[-1]['t_s']
            # Detect exact copied measurements even if session metadata and the
            # absolute board epoch were renamed. This is not proof against an
            # adversary rewriting observations; source provenance remains needed.
            measurement_hash = digest([
                {'relative_t_s': round(r['t_s'] - original_start, 9),
                 'theta_rad': r['theta_rad'], 'cart_acceleration_m_s2': r['cart_acceleration_m_s2'],
                 'valid': r['valid']} for r in rows
            ])
            if measurement_hash in seen_measurements:
                raise ValueError('duplicate measurement series despite different source identities')
            seen_hashes.add(source_hash)
            seen_sessions.add(admission['session_id'])
            seen_clocks.add(admission['clock_id'])
            seen_measurements.add(measurement_hash)
            shift = start - original_start
            for row in rows:
                # Subtract before adding to avoid carrying a large board epoch
                # into a short analysis axis. Nothing is interpolated/resampled.
                converted = dict(row, t_s=start + (row['t_s'] - original_start))
                prepared.append(converted)
            finish = prepared[-1]['t_s']
            inputs.append(dict(spec=str(spec), identity=identity, admission=admission,
                original_start_s=original_start, original_end_s=original_end,
                time_shift_s=shift, analysis_start_s=start, analysis_end_s=finish,
                measurement_sha256=measurement_hash, row_count=len(rows),
                separator_before_s=0.0 if len(inputs) == 0 else INTER_RUN_GAP_S))
            start = finish + INTER_RUN_GAP_S
        result[role] = dict(rows=prepared, inputs=inputs)
    return result


def validation_excitation(rows, inputs, config):
    """A static heldout run cannot certify dynamics through zero forecast error."""
    import numpy as np
    from cartpole_sdk.identification.fit import _segments

    checks = []
    for item in inputs:
        run_id = item['identity']['sha256']
        selected = [row for row in rows if row['run_id'] == run_id]
        segments = _segments(selected, 'magnetic', 'commanded', config)
        span = max((float(np.ptp(q)) for _, q, _, _ in segments), default=0.0)
        accelerations = np.concatenate([a for _, _, a, _ in segments]) if segments else np.array([])
        acceleration_std = float(np.std(accelerations)) if len(accelerations) else 0.0
        checks.append(dict(run_id=run_id, spec=item['spec'], segment_count=len(segments),
            eligible_samples=sum(len(t) for t, _, _, _ in segments),
            angle_span_rad=span, acceleration_std_m_s2=acceleration_std,
            passed=bool(span >= config.min_angle_span_rad and
                acceleration_std >= config.min_acceleration_rms_m_s2)))
    return dict(passed=all(check['passed'] for check in checks), per_run=checks,
        min_angle_span_rad=config.min_angle_span_rad,
        min_acceleration_std_m_s2=config.min_acceleration_rms_m_s2,
        rationale='Each reserved validation run must excite angle and input; static perfect forecasts cannot validate dynamics.')


def analyze(training, validation, *, angle_offset_rad=0.0):
    """Use default FitConfig gates; explicit offset is the sole configuration change."""
    from cartpole_sdk.identification.fit import FitConfig, identify_pendulum
    from cartpole_sdk.identification.workflow import provenance

    if type(angle_offset_rad) not in (float, int) or not math.isfinite(angle_offset_rad):
        raise ValueError('angle offset must be finite')
    batch = prepare_batch(training, validation)
    config = replace(FitConfig(), angle_offset_rad=float(angle_offset_rad))
    canonical = {role: value['rows'] for role, value in batch.items()}
    inputs = {role: value['inputs'] for role, value in batch.items()}
    canonical_hash = digest(canonical)
    supplied = dict(inputs=inputs, canonical_sha256=canonical_hash,
        analysis_clock='constructed monotonic axis per group; no shared physical clock inferred',
        inter_run_gap_s=INTER_RUN_GAP_S, interpolation_across_runs=False)
    fit = identify_pendulum(canonical['training'], canonical['validation'], source='magnetic',
        acceleration_kind='commanded', config=config, provenance=supplied).to_dict()
    supplemental = validation_excitation(canonical['validation'], inputs['validation'], config)
    reasons = list(fit['reasons'])
    if not supplemental['passed']:
        reasons.append('one or more reserved runs fail per-run validation excitation minima')
    report = dict(schema='cartpole-pulse-batch-analysis-v1',
        accepted=bool(fit['accepted'] and supplemental['passed']), reasons=reasons,
        supplemental_validation=supplemental,
        fit=fit, canonical_batches=canonical, canonical_sha256=canonical_hash,
        inputs=inputs, analysis_clock=supplied['analysis_clock'], inter_run_gap_s=INTER_RUN_GAP_S,
        angle_offset=dict(value_rad=float(angle_offset_rad), diagnostic_only=angle_offset_rad != 0.0,
            establishment='Operator supplied; this tool does not establish a global angle calibration.',
            historical_fitted_phase='A frozen historical fitted phase is diagnostic only; never calibration proof.'),
        input_semantics=dict(angle='direct raw magnetic theta; filtered omega omitted',
            acceleration='sampled MCU governor acceleration command; not demand or physical acceleration',
            physical_cart_acceleration_measured=False, metric_cart_gain_established=False,
            gain_interpretation='Command-domain effective input gain includes actuator, estimation and clock effects.'),
        recommended_for_hardware_rl=False, model_installed=False,
        limitations=['No interpolation, regression window or prediction crosses source identity, invalid row or gap.',
            'Batching increases independent window count without increasing each pulse duration or relaxing fit gates.',
            'A statistical pass is conditional commanded-input evidence; physical cart motion and global angle calibration remain unverified.',
            'Nonzero angle-offset results are labeled diagnostic; independently establish their calibration before model use.'],
        provenance=dict(tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            sdk=provenance()))
    report['content_sha256'] = digest(report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--training', action='append', required=True, metavar='LOG',
        help='Repeat for each independently completed training run; JSONL, gzip or archive::member.')
    parser.add_argument('--validation', action='append', required=True, metavar='LOG',
        help='Repeat for the prospectively reserved independent validation runs.')
    parser.add_argument('--output', type=Path, required=True, metavar='NEW.json',
        help='New immutable report including canonical input rows and hashes; rejected fits are saved.')
    parser.add_argument('--angle-offset-rad', type=float, default=0.0,
        help='Explicit independently established offset, default0; historical fitted phase is diagnostic only.')
    args = parser.parse_args(argv)
    try:
        from cartpole_sdk.identification.workflow import write_json
        if args.output.exists():
            raise FileExistsError(f'output exists; preserve earlier evidence: {args.output}')
        report = analyze(args.training, args.validation, angle_offset_rad=args.angle_offset_rad)
        write_json(args.output, report)
        import json
        print(json.dumps(dict(output=str(args.output), accepted=report['accepted'],
            reasons=report['reasons'], canonical_sha256=report['canonical_sha256'],
            content_sha256=report['content_sha256'])))
        return 0 if report['accepted'] else 2
    except (ValueError, TypeError, KeyError, OSError, RuntimeError) as exc:
        print(f'analyze_pulse_batch: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
