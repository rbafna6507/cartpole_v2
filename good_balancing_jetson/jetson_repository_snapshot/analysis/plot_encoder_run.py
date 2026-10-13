#!/usr/bin/env python3
"""Plot wrapped and continuous encoder telemetry, without modifying the source log."""
import argparse, csv, hashlib, io, json, math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from angle_plot import angle_series
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('log', type=Path)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)
    data = a.log.read_bytes()
    data = data[:data.rfind(b'\n') + 1]
    rows = [{k: float(v) for k, v in r.items()} for r in csv.DictReader(io.StringIO(data.decode()))]
    source_events = a.log.with_name(a.log.stem + '_events.jsonl')
    eb = source_events.read_bytes()
    eb = eb[:eb.rfind(b'\n') + 1]
    events = [json.loads(s) for s in eb.decode().splitlines()]
    (a.output / (a.log.stem + '_snapshot.csv')).write_bytes(data)
    (a.output / (a.log.stem + '_events_snapshot.jsonl')).write_bytes(eb)
    t = np.array([(r['t_ms'] - rows[0]['t_ms']) / 1000 for r in rows])
    theta = np.array([r['theta'] for r in rows])
    filtered = np.array([r['theta_dot'] for r in rows])
    modes = np.array([r['mode'] for r in rows])
    dt = np.diff(t)
    if np.any(dt <= 0):
        raise ValueError('Board clock reset/nonmonotonic timestamps; analyze each run segment separately')
    seam = np.abs(np.diff(theta)) > math.pi
    step = (np.diff(theta) + math.pi) % (2 * math.pi) - math.pi
    naive = np.diff(theta) / dt
    corrected = step / dt
    rate = corrected.copy()
    rate[dt > 0.2] = np.nan
    tx, continuous = angle_series(t.tolist(), theta.tolist(), unwrap=True)
    wx, wrapped = angle_series(t.tolist(), theta.tolist())
    tx = np.array(tx)
    continuous = np.array(continuous)
    wx = np.array(wx)
    wrapped = np.array(wrapped)
    params = {}
    for e in events:
        f = e['text'].split()
        if e['direction'] == 'rx' and len(f) == 3 and (f[0] == '='):
            try:
                params.setdefault(f[1], set()).add(float(f[2]))
            except ValueError:
                pass
    raw_note = 'Raw counts are not in the telemetry CSV.'
    raw_rollovers = None
    if len(params.get('encoder_upright_raw', [])) == 1 and len(params.get('encoder_invert', [])) == 1:
        target = next(iter(params['encoder_upright_raw']))
        invert = next(iter(params['encoder_invert']))
        raw = np.rint(theta * 4096 / (2 * math.pi) * (-1 if invert else 1) + target) % 4096
        raw_rollovers = int(np.sum(np.abs(np.diff(raw)) > 2048))
        raw_note = f'Raw counts reconstructed from rounded theta and recorded upright={target:g}, invert={invert:g}; not independent raw measurements.'
    summary = {'source': str(a.log), 'source_sha256': hashlib.sha256(data).hexdigest(), 'events_sha256': hashlib.sha256(eb).hexdigest(), 'samples': len(rows), 'duration_s': float(t[-1]), 'display_seam_crossings': int(sum(seam)), 'reconstructed_raw_rollovers': raw_rollovers, 'raw_note': raw_note, 'naive_derivative_peak_rad_s': float(max(abs(naive))), 'wrap_corrected_derivative_peak_rad_s': float(max(abs(corrected))), 'filtered_rate_peak_rad_s': float(max(abs(filtered))), 'max_sample_gap_s': float(max(dt)), 'unwrap_assumption': 'Less than half a rotation between adjacent samples; gaps over 0.2 s are disconnected, no turns inferred.'}
    active = np.where(modes != 0)[0]
    start = max(0, float(t[active[0]]) - 1) if len(active) else 0
    end = min(float(t[-1]), start + 10)
    zoom = (t >= start) & (t <= end)
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False})
    fig, ax = plt.subplots(3, 1, figsize=(12, 9), layout='constrained', gridspec_kw={'height_ratios': [1.2, 1, 1]})
    ax[0].plot(tx, np.degrees(continuous) + 180, color='#126e82', lw=1.2)
    ax[0].axhline(0, color='#999999', lw=0.6)
    ax[0].set(ylabel='Continuous angle (°)\n0 = hanging down', xlabel='Seconds from log start', title=f'Encoder angle: crossings handled correctly\n{a.log.stem} · {len(rows):,} samples · {sum(seam)} ±180° display crossings')
    for i in range(1, len(t)):
        if modes[i] != 0 and modes[i - 1] == 0:
            following = np.where(modes[i:] == 0)[0]
            stop = t[i + following[0]] if len(following) else t[-1]
            ax[0].axvspan(t[i], stop, color='#c9b47a', alpha=0.18)
    ax[0].axvspan(start, end, color='#126e82', alpha=0.06)
    ax[1].plot(t[zoom], np.degrees(theta[zoom]), color='#d78048', alpha=0.55, lw=0.7, label='Old display: false lines across the seam')
    ax[1].plot(wx, np.degrees(wrapped), color='#126e82', lw=1.4, label='Fixed display: break at ±180°')
    ax[1].set(xlim=(start, end), ylim=(-195, 195), ylabel='Wrapped angle (°)\n0 = upright', title='Same data, zoomed: the vertical orange lines are plotting artifacts')
    ax[1].legend(fontsize=9, loc='upper right')
    ax[2].plot(t[1:], rate, color='#126e82', lw=1, label='Shortest-angle difference / elapsed time')
    ax[2].plot(t, filtered, color='#b66b2e', lw=1.1, alpha=0.85, label='Firmware filtered angular rate')
    ax[2].set(xlim=(start, end), ylabel='Angular rate (rad/s)', xlabel='Seconds from log start')
    ax[2].legend(fontsize=9, loc='upper right')
    for q in ax:
        q.grid(alpha=0.18)
    fig.get_layout_engine().set(rect=(0, 0.07, 1, 0.95))
    fig.text(0.065, 0.02, f'Naive derivative falsely reaches {max(abs(naive)):.1f} rad/s; wrap-corrected sampled derivative peaks at {max(abs(corrected)):.1f} rad/s.\nShading marks commanded motion. Unwrapping changes the display only; it does not correct encoder nonlinearity.', fontsize=10, color='#525a63')
    for ext in ['png', 'svg']:
        fig.savefig(a.output / ('encoder_crossings.' + ext), dpi=170, facecolor='white', bbox_inches='tight')
    (a.output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))
if __name__ == '__main__':
    main()
