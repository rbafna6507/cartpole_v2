#!/usr/bin/env python3
"""Summarize stable, stopped runs without opening a serial port or tuning hardware.

Run from any directory. --write saves reports keyed by the hashes of BOTH logs.
Recently modified, still-active, truncated and reset-spanning logs are deferred.
The scheduled reviewer uses these reports plus tuning_state.json for decisions.
"""
import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[1]


def summarize(path, now=None, settle_s=120):
    path = Path(path)
    sidecar = path.with_name(path.stem + '_events.jsonl')
    files = [path] + ([sidecar] if sidecar.exists() else [])
    before = [(p.stat().st_size, p.stat().st_mtime_ns) for p in files]
    now = time.time() if now is None else now
    if any(now - p.stat().st_mtime < settle_s for p in files):
        return {'status': 'deferred', 'reason': 'log is still being written or settling'}
    raw = [p.read_bytes() for p in files]
    if before != [(p.stat().st_size, p.stat().st_mtime_ns) for p in files]:
        return {'status': 'deferred', 'reason': 'log changed during read'}
    try:
        if any(not b.endswith(b'\n') for b in raw):
            raise ValueError('incomplete final line')
        rows = [{k: float(v) for k, v in row.items()}
                for row in csv.DictReader(io.StringIO(raw[0].decode()))]
        required = {'t_ms', 'mode', 'theta', 'x', 'v', 'accel', 'energy'}
        if not rows or any(not required <= r.keys() or
                           not all(math.isfinite(v) for v in r.values()) for r in rows):
            raise ValueError('missing or nonfinite telemetry')
        if any(b['t_ms'] <= a['t_ms'] for a, b in zip(rows, rows[1:])):
            raise ValueError('clock reset or nonmonotonic telemetry')
        events = [json.loads(line) for line in raw[1].decode().splitlines()] if len(raw) > 1 else []
    except (ValueError, TypeError, UnicodeError) as exc:
        return {'status': 'deferred', 'reason': str(exc)}
    if int(rows[-1]['mode']) not in (0, 4):
        return {'status': 'deferred', 'reason': 'no final stopped/fault telemetry'}
    active = [r for r in rows if int(r['mode']) in (2, 3, 5, 6, 7, 8, 9, 10, 11)]
    if not any(int(r['mode']) in (2,3) for r in active):
        return {'status': 'no_auto_run'}
    params, snapshots, firmware, faults = {}, [], [], []
    for event in events:
        text = event.get('text', '')
        if event.get('direction') == 'rx':
            fields = text.split()
            if len(fields) == 3 and fields[0] == '=':
                try:
                    value = float(fields[2])
                    if math.isfinite(value):
                        params[fields[1]] = value
                except ValueError:
                    pass
            if 'swingup-175mm-' in text and text not in firmware:
                firmware.append(text)
            if text.startswith('!'):
                faults.append(text)
        # UART replies arrive after host transmit records. Snapshot at the
        # firmware's start acknowledgement, after the preceding params reply.
        if event.get('direction') == 'rx' and text.strip() in ('# SWINGUP', '# BALANCE'):
            snapshots.append({'host_time_s': event.get('host_time_s'),
                              'command': 'auto' if text.strip() == '# SWINGUP' else 'bal',
                              'parameters': dict(params)})
    # Only attribute cap fractions when all starts have the same known caps.
    caps = {}
    for key in ('vmax', 'amax_s', 'amax_b', 'jmax'):
        values = {s['parameters'].get(key) for s in snapshots}
        if len(values) == 1 and None not in values:
            caps[key] = values.pop()
    longest = current = duration = 0.0
    gaps = []
    for a, b in zip(rows, rows[1:]):
        dt = (b['t_ms'] - a['t_ms']) / 1000
        gaps.append(dt)
        if int(a['mode']) in (2, 3, 5, 6, 7, 8, 9, 10, 11):
            duration += dt
        if int(a['mode']) == 3 and int(b['mode']) == 3 and dt <= .1:
            current += dt
            longest = max(longest, current)
        else:
            current = 0
    warnings = []
    if not snapshots or len(caps) != 4:
        warnings.append('missing or mixed parameter snapshots; do not infer cap saturation')
    zero_lines = sum('zeroing: hold' in e.get('text', '') for e in events)
    if zero_lines > 10:
        warnings.append(f'{zero_lines} startup zeroing messages; inspect event timing before attributing resets')
    if max(gaps, default=0) > .1:
        warnings.append('telemetry gap exceeds 100 ms; compare timing before tuning')
    lift = lambda r: 180 - abs(math.degrees(math.atan2(math.sin(r['theta']), math.cos(r['theta']))))
    first_t, last_t = active[0]['t_ms'], active[-1]['t_ms']
    report = {
        'status': 'complete', 'source': str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
        'source_sha256': {p.name: hashlib.sha256(b).hexdigest() for p, b in zip(files, raw)},
        'firmware_messages': firmware, 'start_snapshots': snapshots,
        'samples': len(rows), 'active_duration_s': duration,
        'max_lift_from_down_deg': max(map(lift, active)),
        'first_10s_max_lift_deg': max(lift(r) for r in active if r['t_ms'] < first_t + 10000),
        'last_10s_max_lift_deg': max(lift(r) for r in active if r['t_ms'] > last_t - 10000),
        'longest_balance_mode_s': longest,
        'spin_recovery_duration_s': sum((b['t_ms']-a['t_ms'])/1000 for a,b in zip(rows,rows[1:]) if int(a['mode']) in (7,8,9)),
        'rail_recovery_duration_s': sum((b['t_ms']-a['t_ms'])/1000 for a,b in zip(rows,rows[1:]) if int(a['mode']) in (5,6)),
        'peak_commanded_speed_m_s': max(abs(r['v']) for r in active),
        'peak_commanded_accel_m_s2': max(abs(r['accel']) for r in active),
        'peak_inferred_position_m': max(abs(r['x']) for r in active),
        'fraction_inferred_position_over_100mm': sum(abs(r['x']) > .1 for r in active) / len(active),
        'max_telemetry_gap_s': max(gaps, default=0),
        'fault_mode_seen': any(int(r['mode']) == 4 for r in rows),
        'diagnostic_errors': faults, 'data_quality_notes': warnings,
        'measurement_note': 'Only pendulum angle is measured. Cart x is pulse-inferred; v and accel are commands. Balance-mode duration alone is not proof of stable balance.',
    }
    if caps.get('vmax', 0) > 0:
        report['fraction_at_speed_cap'] = sum(abs(r['v']) >= .99*caps['vmax'] for r in active)/len(active)
    if all(caps.get(k, 0) > 0 for k in ('amax_s', 'amax_b')):
        report['fraction_at_accel_cap'] = sum(abs(r['accel']) >= .99*caps['amax_s' if int(r['mode']) == 2 else 'amax_b'] for r in active)/len(active)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('paths', nargs='*', type=Path)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    for path in args.paths or sorted((ROOT / 'logs').glob('run_*.csv')):
        report = summarize(path.resolve())
        target = ROOT / 'analysis' / 'run_reviews' / (path.stem + '.json')
        unchanged = target.exists() and json.loads(target.read_text()) == report and report['status'] == 'complete'
        if args.write and report['status'] == 'complete' and not unchanged:
            target.parent.mkdir(exist_ok=True)
            target.write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps({'run': path.name, 'status': report['status'], 'unchanged': unchanged,
                          'report': str(target) if report['status'] == 'complete' else None,
                          'reason': report.get('reason')}))


if __name__ == '__main__':
    main()
