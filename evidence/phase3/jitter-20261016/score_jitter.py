#!/usr/bin/env python3
"""Read-only scorer for native AUTO JSON(.gz) reports. Requires Python 3 + NumPy.
Default comparison: first 15 s beginning 2 s into the longest balance bout.
No rig imports, networking, commands, or hardware operations.
"""
import argparse, glob, gzip, json, pathlib
import numpy as np

BANDS = ((0, 2), (2, 4), (4, 9), (9, 30), (30, 100))
COLS = ('theta', 'angle_hat', 'omega', 'x', 'velocity', 'acceleration', 'demand')

def spectrum(y, fs=250.):
    n = min(2048, len(y))
    if n < 16:
        return np.array([]), np.array([])
    # Periodic Hann, 50% overlap, segment-mean removal, same scaling as scipy.welch.
    win = .5 - .5*np.cos(2*np.pi*np.arange(n)/n)
    starts = range(0, len(y)-n+1, max(1, n//2))
    parts = [np.abs(np.fft.rfft((y[i:i+n]-np.mean(y[i:i+n]))*win))**2
             for i in starts]
    p = np.mean(parts, axis=0)/(fs*np.sum(win**2))
    p[1:-1 if n % 2 == 0 else None] *= 2
    return np.fft.rfftfreq(n, 1/fs), p

def metrics(y):
    f, p = spectrum(y)
    bands = {}
    for a, b in BANDS:
        m = (f >= a) & (f < b)
        bands[f'{a}-{b}'] = float(np.sqrt(np.trapezoid(p[m], f[m]))) if sum(m)>1 else None
    fast = (f >= 4) & (f < 30)
    return dict(rms=float(np.sqrt(np.mean(y*y))), mean=float(np.mean(y)),
                max_abs=float(np.max(abs(y))), bands_rms=bands,
                fast_peak_hz=float(f[fast][np.argmax(p[fast])]) if any(fast) else None)

def gains(p):
    L=p['leff']; b1=2*p['pz']*p['pw']; b0=p['pw']**2
    c1=-(p['pc1']+p['pc2']); c0=p['pc1']*p['pc2']
    k3=-b0*c0*L/9.81; k4=-(b1*c0+b0*c1)*L/9.81
    k1=L*k3-9.81-L*(b0+b1*c1+c0); k2=L*(k4-b1-c1)
    return -np.array([k1,k2,k3,k4])

def score(path, skip=2., window=15.):
    with (gzip.open(path, 'rt') if str(path).endswith('.gz') else open(path)) as f:
        report = json.load(f)
    rows = sorted({s['unwrapped_tick']:s for s in report['states']}.values(),
                  key=lambda s:s['unwrapped_tick'])
    if not rows:
        return dict(path=str(path), error='No states')
    origin = report['motion_start']['unwrapped_tick']
    t = np.array([(s['unwrapped_tick']-origin)/1000 for s in rows])
    mode = np.array([s['mode'] for s in rows])
    d = {k:np.array([s[k] for s in rows]) for k in COLS}
    dt = float(np.median(np.diff(t)))
    ids = np.flatnonzero(mode == 3)
    bouts = [e for e in np.split(ids, np.flatnonzero(np.diff(ids)>1)+1) if len(e)]
    def state(i):
        x, v = float(d['x'][i]), float(d['velocity'][i])
        return dict(time_s=float(t[i]), **{k:float(d[k][i]) for k in COLS},
                    inward_velocity_m_s=float(-np.sign(x)*v))
    def duration(e):
        return float(t[e[-1]]-t[e[0]])
    deadline = report.get('requested_s')
    ret = np.flatnonzero(mode == 14)
    after_return_idle = bool(len(ret) and any((mode==0)&(t>t[ret[-1]])))
    final = report.get('final') or rows[-1]
    centered = abs(final['x']) <= .001 and abs(final['velocity']) <= .005 and abs(final['acceleration']) <= .1
    info0 = report.get('applied_info') or report.get('info') or {}
    info1 = report.get('final_info') or {}
    i2c_delta = (info1['i2c_errors']-info0['i2c_errors']) if 'i2c_errors' in info0 and 'i2c_errors' in info1 else None
    o = dict(path=str(path), run=pathlib.Path(path).parent.name,
        parameters={k:report['parameters'].get(k) for k in ['pw','pz','pc1','pc2','bw','jmax','ke','approach_v','catch_a','catch_v','catch_r']},
        report_ok=bool(report.get('ok')), report_error=report.get('error'), requested_s=deadline,
        hanging_offset_rad=(report.get('settling') or {}).get('mean_down_angle'),
        initial_state=report.get('motion_start'), balance_bouts=[dict(capture=state(e[0]), duration_lower_bound_s=duration(e), exit_time_s=float(t[e[-1]+1]) if e[-1]+1<len(t) else None, exit_mode=int(mode[e[-1]+1]) if e[-1]+1<len(t) else None) for e in bouts],
        capture_s=float(t[ids[0]]) if len(ids) else None,
        continuous_hold_lower_bound_s=max([duration(e) for e in bouts],default=0.),
        total_balance_lower_bound_s=sum(duration(e) for e in bouts),
        balanced_at_deadline=bool(deadline is not None and any((mode==3)&(t>=deadline-.020)&(t<=deadline+.010))),
        full_return=bool(report.get('ok') and len(ret) and after_return_idle and centered and final['fault']==0),
        return_start_s=float(t[ret[0]]) if len(ret) else None,
        final_state=final, rail_recovery_samples=int(sum(np.isin(mode,[5,6]))),
        health=dict(max_fault=max(s.get('fault',0) for s in rows), max_misses=max(s.get('misses',0) for s in rows), i2c_error_delta=i2c_delta, records_dropped=report.get('records_dropped')),
        scorer=dict(skip_after_capture_s=skip, common_window_s=window, fs_hz=250, nperseg=2048,
                    notes='Longest balance bout; fixed first steady window. Gaps interpolated only for spectra. Jerk is native interval-average; not full 1 kHz instantaneous duty. Acceleration/velocity are commanded, not independently measured.'))
    if not bouts:
        return o
    e = max(bouts, key=duration); start = float(t[e[0]]+skip); wanted_end=start+window
    end = min(wanted_end, float(t[e[-1]]+dt))
    o['comparison_window'] = dict(start_s=start, requested_end_s=wanted_end, actual_end_s=end,
        complete=bool(t[e[-1]]+dt >= wanted_end-.001), capture=state(e[0]))
    if end-start < 1:
        o['comparison_window']['error']='Less than 1 s after transient exclusion'
        return o
    # Use surrounding native samples for interpolation; never cross a mode boundary.
    valid = e[(t[e]>=start-dt)&(t[e]<end+dt)]
    grid = np.arange(max(start,t[valid[0]]), min(end,t[valid[-1]]+.000001), .004)
    s = {k:np.interp(grid,t[valid],d[k][valid]) for k in COLS}
    gap = float(max(np.diff(t[valid]))) if len(valid)>1 else None
    o['comparison_window'].update(samples=len(grid), native_samples=len(valid),
        max_native_gap_s=gap, spectral_comparable=bool(o['comparison_window']['complete'] and gap is not None and gap<=.020))
    o['metrics'] = {k:metrics(s[k]) for k in COLS}
    jerk = np.diff(d['acceleration'][valid])/np.diff(t[valid])
    request_jerk = np.diff(d['demand'][valid])/np.diff(t[valid])
    limit = report['parameters']['jmax']
    o['jerk'] = dict(limit=limit, sampled_limit_fraction=float(np.mean(abs(jerk)>.9666666667*limit)),
        sampled_rms=float(np.sqrt(np.mean(jerk**2))), requested_rms=float(np.sqrt(np.mean(request_jerk**2))),
        requested_abs_p95=float(np.percentile(abs(request_jerk),95)))
    terms = gains(report['parameters'])[:,None]*np.array([s[k] for k in ['angle_hat','omega','x','velocity']])
    o['demand_terms'] = {k:metrics(v) for k,v in zip(['angle','rate','position','velocity'],terms)}
    o['tracking_error_rms'] = float(np.sqrt(np.mean((s['demand']-s['acceleration'])**2)))
    o['reconstruction_error_rms'] = float(np.sqrt(np.mean((s['demand']-sum(terms))**2)))
    o['angle_rms_deg'] = float(np.degrees(o['metrics']['theta']['rms']))
    return o

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('paths',nargs='+',help='JSON/gz reports, directories, or glob patterns')
    p.add_argument('--json-output');p.add_argument('--skip',type=float,default=2.);p.add_argument('--window',type=float,default=15.)
    args=p.parse_args();paths=[]
    for arg in args.paths:
        for s in sorted(glob.glob(arg,recursive=True)):
            q=pathlib.Path(s)
            paths.extend(sorted(q.rglob('report.json*')) if q.is_dir() else [q])
    paths=list(dict.fromkeys(paths))
    if not paths:p.error('No reports matched')
    results=[score(q,args.skip,args.window) for q in paths]
    if args.json_output:
        pathlib.Path(args.json_output).write_text(json.dumps(results,indent=2)+'\n')
    print('run | cap s | longest s | deadline/return | common window | theta RMS deg | peak | D/A 4–9 RMS | D/A 9–30 RMS | jerk % | x max m')
    for o in results:
        if 'metrics' not in o:print(o.get('run',o['path']),'NO STEADY METRICS');continue
        m=o['metrics']; w=o['comparison_window'];fmt=lambda x:f'{x:.3f}'
        values=[o['run'],fmt(o['capture_s']),fmt(o['continuous_hold_lower_bound_s']),f"{o['balanced_at_deadline']}/{o['full_return']}",f"{w['start_s']:.3f}..{w['actual_end_s']:.3f} {'OK' if w['spectral_comparable'] else 'INCOMPLETE/GAPS'}",fmt(o['angle_rms_deg']),fmt(m['demand']['fast_peak_hz']),'/'.join(fmt(m[k]['bands_rms']['4-9']) for k in ['demand','acceleration']),'/'.join(fmt(m[k]['bands_rms']['9-30']) for k in ['demand','acceleration']),f"{100*o['jerk']['sampled_limit_fraction']:.1f}",fmt(m['x']['max_abs'])]
        print(' | '.join(values))

if __name__=='__main__':main()
