#!/usr/bin/env python3
"""Refit same-side, 5–20 degree decay cycles without changing original captures."""
import hashlib
import json
from pathlib import Path
import numpy as np
from scipy.signal import find_peaks, savgol_filter

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'pendulum_characterization/legacy_geometry_unverified/2026-09-15'
OUT = ROOT / 'pendulum_characterization/125mm_11p05g/2026-09-15'
CAPTURES = tuple(p.stem.removeprefix('pendulum_') for p in sorted(DATA.glob('pendulum_*.csv')))

def fit():
    runs = []
    excluded = []
    for stamp in CAPTURES:
        path = DATA / f'pendulum_{stamp}.csv'
        data = np.genfromtxt(path, delimiter=',', names=True)
        time = (data['t_us'] - data['t_us'][0]) * 1e-6
        angle = np.unwrap(data['theta'])
        angle -= np.median(angle[-1000:])
        angle = savgol_filter(angle, 19, 3)
        cycles = []
        for sign in (-1, 1):
            peaks, _ = find_peaks(sign*angle, distance=250, prominence=0.025)
            for first, last in zip(peaks[:-1], peaks[1:]):
                a, b = abs(angle[first]), abs(angle[last])
                period = time[last] - time[first]
                if (sign*angle[first] > 0 and sign*angle[last] > 0
                    and np.radians(5) <= min(a, b)
                    and max(a, b) <= np.radians(20) and b < a
                    and 0.6 < period < 1.1):
                    cycles.append(dict(start_s=float(time[first]), end_s=float(time[last]),
                                       start_amplitude_deg=float(np.degrees(a)),
                                       end_amplitude_deg=float(np.degrees(b)), period_s=float(period)))
        if len(cycles) < 6:
            excluded.append(dict(source=str(path.relative_to(ROOT)),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),cycle_count=len(cycles),reason='Fewer than six qualifying low-angle decay cycles'))
            continue
        period = float(np.median([c['period_s'] for c in cycles]))
        decrements = [np.log(c['start_amplitude_deg']/c['end_amplitude_deg']) for c in cycles]
        # Descriptive equivalent damping, not a claim that pivot friction is purely viscous.
        damping = float(2*np.median(decrements)/period)
        runs.append(dict(source=str(path.relative_to(ROOT)), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                         cycle_count=len(cycles), period_s=period,
                         effective_length_m=9.81*(period/(2*np.pi))**2,
                         equivalent_viscous_decay_per_s=damping, cycles=cycles))
    length = float(np.median([r['effective_length_m'] for r in runs]))
    return dict(physical_length_mm=125, pendulum_mass_g=11.05, end_mass_count=2, end_mass_each_g=5.85,
                provenance='User corrected original 100 mm label to 125 mm and identified pre-175 mm captures as this arm on 2026-09-17; same two end weights. Raw files remain at their historical paths.',
                method='Same-side decaying peaks, both amplitudes 5–20 degrees; median period per run, then median effective length across runs.',
                smoothing='19-sample third-order Savitzky–Golay filter at approximately 500 Hz; equilibrium from final 1000 samples.',
                limitations='Not a torque calibration. Pivot friction and encoder asymmetry remain; firmware uses effective length rounded to 1 mm. Damping is descriptive, not used as an exact friction compensation.',
                total_cycles=sum(r['cycle_count'] for r in runs), selected_effective_length_m=length,
                firmware_effective_length_m=round(length,3),
                period_s=float(np.median([r['period_s'] for r in runs])),
                equivalent_viscous_decay_per_s=float(np.median([r['equivalent_viscous_decay_per_s'] for r in runs])),
                runs=runs,excluded=excluded)

if __name__ == '__main__':
    result = fit()
    output = OUT / 'controller_fit.json'
    OUT.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(f"{result['total_cycles']} cycles; L_eff={result['selected_effective_length_m']:.6f} m; firmware {result['firmware_effective_length_m']:.3f} m")
    print(output)
