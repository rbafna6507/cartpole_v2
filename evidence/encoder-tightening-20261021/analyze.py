#!/usr/bin/env python3
"""Offline post-tightening sensor diagnosis. Never promotes hardware acceptance.

Usage: python analyze.py --input RUN_OR_CAMPAIGN --output NEW_DIRECTORY
Requires numpy and matplotlib. Reads direct Rig states/INFO and raw image marker
geometry, never camera-calibrated theta, fused angles, or encoder mirror packets.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path

import numpy as np

TAU = 2 * math.pi
GAP_S = .030
CAMERA_GAP_S = .075
RESTS = ('initial_rest', 'before_auto_rest', 'after_auto_rest')
AUTO_MODES = (2, 3, 5, 6, 7, 8, 9, 10, 11)


def wrap(x):
    return (np.asarray(x) + math.pi) % TAU - math.pi


def stats(values):
    a = np.asarray(values, dtype=float)
    a = a[np.isfinite(a)]
    if not len(a):
        return None
    return dict(n=len(a), median=float(np.median(a)), p05=float(np.percentile(a, 5)),
                p95=float(np.percentile(a, 95)), min=float(a.min()), max=float(a.max()),
                rms=float(np.sqrt(np.mean(a*a))))


def circular_summary(values, period=TAU):
    a = np.asarray(values, dtype=float)
    a = a[np.isfinite(a)]
    if not len(a):
        return None
    phase = a * TAU / period
    anchor = math.atan2(float(np.sin(phase).mean()), float(np.cos(phase).mean()))
    relative = wrap(phase-anchor) * period / TAU
    middle = float(np.median(relative))
    median = (anchor*period/TAU + middle) % period
    if period == TAU:
        median = float(wrap(median))
    elif math.isclose(median, period, abs_tol=1e-9):
        median = 0.
    return dict(n=len(a), median=median, p95_minus_p05=float(np.percentile(relative,95)-np.percentile(relative,5)),
                span=float(np.ptp(relative)), std=float(np.std(relative)),
                p95_abs_about_median=float(np.percentile(abs(relative-middle),95)))


def interpolate(t, values, query, angular=False, max_gap=GAP_S):
    """Interpolate only inside a known short interval, never across a dropout."""
    t, v, q = np.asarray(t), np.asarray(values), np.asarray(query)
    out = np.full(q.shape, np.nan)
    if len(t) < 2:
        return out, np.zeros(q.shape, dtype=bool)
    right = np.searchsorted(t, q, side='right')
    right = np.clip(right, 1, len(t)-1)
    left = right-1
    dt = t[right]-t[left]
    valid = (q >= t[left]) & (q <= t[right]) & (dt > 0) & (dt <= max_gap+1e-9)
    valid &= np.isfinite(v[left]) & np.isfinite(v[right])
    delta = wrap(v[right]-v[left]) if angular else v[right]-v[left]
    out[valid] = v[left[valid]] + delta[valid]*(q[valid]-t[left[valid]])/dt[valid]
    if angular:
        out = wrap(out)
    return out, valid


def map_board_clock(board, receipts):
    """Fit drift to one-second receipt minima and use a 1st-percentile offset.

    This is a lower-envelope receipt proxy; it cannot identify USB transit time
    or sensor exposure latency. The residual lag fit absorbs a constant delay.
    """
    b = np.asarray(board)-board[0]
    h = np.asarray(receipts)-receipts[0]
    groups = np.floor(b).astype(int)
    indexes = [np.flatnonzero(groups == group)[np.argmin((h-b)[groups == group])] for group in np.unique(groups)]
    slope = float(np.polyfit(b[indexes], h[indexes], 1)[0]) if len(indexes) >= 4 else 1.
    unconstrained_slope = slope
    slope = float(np.clip(slope, .999, 1.001))
    offset = float(np.percentile(h-slope*b, 1))
    mapped = receipts[0] + offset + slope*b
    return mapped, dict(method='1-second receipt minima drift fit, 1st-percentile intercept',
        board_origin_s=float(board[0]), host_origin_s=float(receipts[0]+offset), scale=slope,
        drift_ppm=(slope-1)*1e6, unconstrained_scale=unconstrained_slope,
        lower_envelope_bins=len(indexes), receipt_delay_s=stats(receipts-mapped),
        limitation='Host receipt lower envelope is not independently measured board-to-host synchronization.')


def durations(t, mask, segments=None, max_gap=GAP_S):
    t, mask = np.asarray(t), np.asarray(mask, dtype=bool)
    total = longest = current = 0.
    for i in range(1, len(t)):
        gap = t[i]-t[i-1]
        valid = mask[i] and mask[i-1] and 0 < gap <= max_gap+1e-9
        if segments is not None:
            valid = valid and segments[i] == segments[i-1]
        current = current + gap if valid else 0.
        if valid:
            total += gap
        longest = max(longest, current)
    return dict(total_s=float(total), longest_continuous_s=float(longest), sample_count=int(mask.sum()),
                interval_rule='Both endpoints pass; gaps break runs; no duration extrapolated beyond last sample.')


def read_json(path):
    return json.loads(path.read_text())


def read_lines(path):
    return [json.loads(line) for line in path.open() if line.strip()]


def camera_clock(row, anchors):
    source = row['vision']['t']
    if not anchors:
        return source
    at = [a['server_monotonic_s'] for a in anchors]
    off = [a['offset_ns']/1e9 for a in anchors]
    return source + float(np.interp(source, at, off))


def load_trial(path):
    report = read_json(path/'report.json')
    files = sorted(path.glob('rig*.jsonl'))
    if not files:
        files = sorted((path/'raw').glob('rig*.jsonl'))
    rows = [row for file in files for row in read_lines(file)]
    states = [row['state'] for row in rows if row.get('type') == 'state']
    if len({s['sid'] for s in states}) != 1:
        raise ValueError(f'{path}: require exactly one direct Rig session')
    states = sorted({s['unwrapped_us']:s for s in states}.values(), key=lambda s:s['unwrapped_us'])
    if len(states) < 2:
        raise ValueError(f'{path}: insufficient direct Rig states')
    board = np.array([s['unwrapped_us']/1e6 for s in states])
    receipt = np.array([s['received_ns']/1e9 for s in states])
    mapped, clock = map_board_clock(board, receipt)
    infos = [row['info'] for row in rows if row.get('type') == 'info']
    events = report.get('events', [])
    if not events:
        events = [r for r in rows if r.get('type') in ('encoder_check_phase','baseline_auto_start')]
    refs = {i['encoder_upright_raw'] for i in infos}
    if not refs and 'info_before' in report:
        refs = {report['info_before']['encoder_upright_raw']}
    reference = next(iter(refs)) if len(refs) == 1 else None
    camera_report_path = path/'vision-report.json'
    camera_report = read_json(camera_report_path) if camera_report_path.exists() else report.get('camera', {})
    anchors = [v for k,v in camera_report.get('clock_sync', {}).items() if isinstance(v,dict) and 'offset_ns' in v]
    anchors.sort(key=lambda v:v['server_monotonic_s'])
    raw_camera = read_lines(path/'vision.ndjson') if (path/'vision.ndjson').exists() else []
    accepted, rejected, segment, previous, seen = [], Counter(), 0, None, set()
    for row in raw_camera:
        v = row.get('vision') or {}
        key = (v.get('seq'),v.get('t'))
        if key in seen:
            rejected['duplicate_frame'] += 1
            continue
        seen.add(key)
        reason = None
        if (v.get('detected') is not True or v.get('stale') is not False or v.get('worker_error') or
                v.get('detection_status','measured') != 'measured'):
            reason = 'missing_or_invalid_track'
        try:
            t, host, age = float(v['t']),float(row['host_t']),float(v['age_since_host_read_s'])
            confidence = float(v['confidence'])
            pivot, bob = np.asarray(v['pivot_px'],dtype=float), np.asarray(v['bob_px'],dtype=float)
            if pivot.shape != (2,) or bob.shape != (2,) or not np.all(np.isfinite([*pivot,*bob,t,host,age,confidence])):
                reason = reason or 'nonfinite_geometry_or_clock'
            dx,dy = bob-pivot
            length = float(math.hypot(dx,dy))
            if not -.01 <= host-t <= .15 or not 0 <= age <= .15:
                reason = reason or 'source_not_fresh'
            if confidence < .8:
                reason = reason or 'confidence_below_0.8'
            if length <= 5:
                reason = reason or 'degenerate_geometry'
            if reason is None:
                local = camera_clock(row,anchors)
                if previous is not None and local <= previous:
                    reason = 'camera_time_not_increasing'
                received = row.get('collector_received_ns')
                if type(received) is not int or not -.01 <= received/1e9-local <= .15:
                    reason = 'collector_source_age_invalid'
        except (KeyError,TypeError,ValueError,OverflowError):
            reason = reason or 'missing_geometry_or_clock'
        if reason:
            rejected[reason] += 1
            segment += 1
            continue
        if previous is not None and local-previous > CAMERA_GAP_S:
            segment += 1
        accepted.append(dict(t=local,source_t=t,angle=math.atan2(dx,-dy),length=length,
            pivot_x=float(pivot[0]),pivot_y=float(pivot[1]),confidence=confidence,seq=v['seq'],segment=segment))
        previous = local
    median_length = float(np.median([c['length'] for c in accepted])) if accepted else None
    camera, previous_segment, output_segment = [], None, 0
    for c in accepted:
        if not .8*median_length <= c['length'] <= 1.2*median_length:
            rejected['length_outside_20pct_median'] += 1
            output_segment += 1
            continue
        if previous_segment != c['segment']:
            output_segment += 1
        previous_segment = c['segment']
        camera.append(dict(c,segment=output_segment))
    sources = files + [path/'report.json'] + [p for p in (path/'vision.ndjson', camera_report_path) if p.exists()]
    return dict(name=path.name,path=path,report=report,states=states,board=board,host=mapped,receipt=receipt,
        infos=infos,events=events,reference=reference,clock=clock,camera=camera,sources=sources,
        camera_report=camera_report,raw_camera=raw_camera,filter_report=dict(raw_records=len(raw_camera),accepted_frames=len(camera),
            rejected=dict(rejected),median_length_px=median_length,clock_anchors=anchors,
            clock_assumption=None if anchors else 'No clock anchors: assume camera and Rig share host monotonic origin.'))


def phase_bounds(trial, label):
    start = next((e['host_monotonic_ns']/1e9 for e in trial['events'] if e.get('event') == label+'_start'),None)
    end = next((e['host_monotonic_ns']/1e9 for e in trial['events'] if e.get('event') == label+'_end'),None)
    return (start,end) if start is not None and end is not None and end > start else None


def rest_report(trial,label):
    bounds = phase_bounds(trial,label)
    if bounds is None:
        return dict(available=False,reason='No explicit start/end phase markers; no rest inferred from arbitrary idle states.')
    lo,hi = bounds
    ss = [s for s in trial['states'] if lo <= s['received_ns']/1e9 <= hi]
    cc = [c for c in trial['camera'] if lo <= c['t'] <= hi]
    ii = [i for i in trial['infos'] if lo <= i['received_ns']/1e9 <= hi and isinstance(i.get('encoder_raw'),int)]
    raw_frames = {(r.get('vision',{}).get('seq'),r.get('vision',{}).get('t')) for r in trial.get('raw_camera',[])
                  if isinstance(r.get('vision',{}).get('t'),(int,float)) and lo <= camera_clock(r,trial.get('filter_report',{}).get('clock_anchors',[])) <= hi}
    fraction = len(cc)/len(raw_frames) if raw_frames else None
    camera_duration = cc[-1]['t']-cc[0]['t'] if len(cc)>1 else 0.
    camera_coverage = fraction is not None and fraction >= .8 and len(cc)>=30 and camera_duration >= .75*(hi-lo)
    ref = trial['reference']
    state_counts = [(ref+s['theta']*4096/TAU)%4096 for s in ss] if ref is not None else []
    healthy = bool(ss) and all(s['mode']==0 and s['flags']&3==1 and s['fault']==0 for s in ss)
    encoder_quiet = bool(healthy and len(ss)>=100 and ss[-1]['received_ns']-ss[0]['received_ns']>=4_500_000_000
        and circular_summary([s['theta'] for s in ss])['span']<=.03 and max(abs(s['omega']) for s in ss)<=.15
        and np.ptp([s['x'] for s in ss])<=.003)
    return dict(available=True,host_window_s=list(bounds),state_samples=len(ss),camera_samples=len(cc),
        camera_raw_unique_frames=len(raw_frames),camera_valid_fraction=fraction,
        camera_valid_duration_s=camera_duration,camera_coverage_qualified=camera_coverage,
        camera_gap_s=stats(np.diff([c['t'] for c in cc])),
        native_info_counts_all=circular_summary([i['encoder_raw'] for i in ii],4096),
        native_info_unchanged_duration_us=stats([i.get('encoder_raw_age_us',np.nan) for i in ii]),
        native_info_timing_semantics='encoder_raw_age_us is time since raw COUNT last changed, not I2C acquisition age. Repeated INFO readbacks are not proof of independent sensor acquisitions.',
        state_reconstructed_counts=circular_summary(state_counts,4096),
        encoder_theta_rad=circular_summary([s['theta'] for s in ss]),
        camera_image_upright_rad=circular_summary([c['angle'] for c in cc]),
        encoder_rate_abs_rad_s=stats([abs(s['omega']) for s in ss]),
        cart_step_position_m=stats([s['x'] for s in ss]),
        camera_pivot_x_px=stats([c['pivot_x'] for c in cc]),
        camera_pivot_y_px=stats([c.get('pivot_y',np.nan) for c in cc]),camera_length_px=stats([c['length'] for c in cc]),
        disabled_and_healthy=healthy,encoder_rest_qualified=encoder_quiet)


def rest_difference(before,after):
    out = dict(available=False,interpretation='Encoder shift minus raw-camera pose shift is a differential sensor discrepancy, not proof of mechanical slip or a calibration.')
    if not all(r.get('state_reconstructed_counts') and r.get('camera_image_upright_rad') for r in (before,after)):
        return out
    state = float(wrap((after['state_reconstructed_counts']['median']-before['state_reconstructed_counts']['median'])*TAU/4096)*4096/TAU)
    camera = float(wrap(after['camera_image_upright_rad']['median']-before['camera_image_upright_rad']['median']))
    out.update(available=True,encoder_rest_qualified=all(r.get('encoder_rest_qualified',False) for r in (before,after)),
        camera_coverage_qualified=all(r.get('camera_coverage_qualified',False) for r in (before,after)),
        state_shift_counts=state,camera_change_rad=camera,
        camera_change_equivalent_counts=camera*4096/TAU,state_minus_camera_shift_counts=state-camera*4096/TAU,
        state_minus_camera_shift_deg=(state*TAU/4096-camera)*180/math.pi)
    if all(r.get('native_info_counts_all') for r in (before,after)):
        native = float(wrap((after['native_info_counts_all']['median']-before['native_info_counts_all']['median'])*TAU/4096)*4096/TAU)
        out.update(native_info_shift_counts=native,native_info_minus_camera_shift_counts=native-camera*4096/TAU)
    return out


def paired(trial,lag):
    camera = trial['camera']
    if not camera:
        return []
    query = np.array([c['t']+lag for c in camera])
    t, states = trial['host'],trial['states']
    theta,valid = interpolate(t,np.array([s['theta'] for s in states]),query,angular=True)
    rate,_ = interpolate(t,np.array([s['omega'] for s in states]),query)
    x,_ = interpolate(t,np.array([s['x'] for s in states]),query)
    velocity,_ = interpolate(t,np.array([s['velocity'] for s in states]),query)
    ix = np.clip(np.searchsorted(t,query,side='right')-1,0,len(t)-1)
    telemetry_segment = np.cumsum(np.r_[0,np.diff(t)>GAP_S+1e-9])
    output = []
    last_camera = None
    for i,c in enumerate(camera):
        camera_rate = None
        if last_camera is not None and c['segment']==last_camera['segment'] and 0 < c['t']-last_camera['t'] <= CAMERA_GAP_S:
            camera_rate = float(wrap(c['angle']-last_camera['angle'])/(c['t']-last_camera['t']))
        last_camera = c
        if not valid[i] or states[ix[i]]['fault'] or not states[ix[i]]['flags']&1:
            continue
        output.append(dict(host_s=c['t'],encoder_query_host_s=float(query[i]),encoder_rad=float(theta[i]),camera_rad=c['angle'],
            residual_rad=float(wrap(c['angle']-theta[i])),encoder_rate_rad_s=float(rate[i]),camera_rate_rad_s=camera_rate,
            cart_step_m=float(x[i]),cart_step_velocity_m_s=float(velocity[i]),mode=states[ix[i]]['mode'],
            camera_seq=c['seq'],segment=int(c['segment']*(len(t)+1)+telemetry_segment[ix[i]]),confidence=c['confidence'],length_px=c['length']))
    return output


def discrepancy(rows):
    if not rows:
        return dict(n=0)
    residual = np.array([r['residual_rad'] for r in rows])
    center = circular_summary(residual)['median']
    centered = wrap(residual-center)
    return dict(n=len(rows),raw_rms_deg=float(np.degrees(np.sqrt(np.mean(residual**2)))),
        raw_abs_p95_deg=float(np.degrees(np.percentile(abs(residual),95))),
        median_camera_minus_encoder_deg=float(np.degrees(center)),
        centered_rms_deg=float(np.degrees(np.sqrt(np.mean(centered**2)))),
        centered_abs_p95_deg=float(np.degrees(np.percentile(abs(centered),95))))


def fit_lag(trial):
    scores = []
    for lag in np.linspace(-.1,.1,201):
        rows = [r for r in paired(trial,lag) if r['mode'] in (2,3) and .3 <= abs(r['encoder_rate_rad_s']) <= 20]
        if len(rows) < 50:
            continue
        residual = np.array([r['residual_rad'] for r in rows])
        center = circular_summary(residual)['median']
        error = abs(wrap(residual-center))
        error = error[error <= np.percentile(error,95)]
        scores.append(dict(lag_s=float(lag),trimmed_centered_rms_rad=float(np.sqrt(np.mean(error**2))),n=len(rows)))
    if not scores:
        return dict(available=False,lag_s=0.,training_trial=trial['name'],reason='Fewer than 50 moving AUTO pairs; zero lag is an explicit unfit fallback.')
    best = min(scores,key=lambda r:r['trimmed_centered_rms_rad'])
    support = [s['lag_s'] for s in scores if s['trimmed_centered_rms_rad'] <= best['trimmed_centered_rms_rad']*1.05+1e-8]
    return dict(available=True,**best,training_trial=trial['name'],frozen_for_later_trials=True,
        boundary_optimum=abs(best['lag_s'])>=.0995,within_5pct_objective_range_s=[min(support),max(support)],
        objective='First AUTO trial only; modes2/3; 0.3<=|firmware omega|<=20; residual centered per lag, largest5% removed.',
        convention='Compare camera at source t to encoder at mapped host t+lag. A negative lag means camera corresponds to earlier encoder data.',
        limitation='Descriptive timing alignment, not exposure-latency calibration. Support range is not a confidence interval.',grid=scores)


def trial_summary(trial,lag):
    states,host = trial['states'],trial['host']
    mode = np.array([s['mode'] for s in states])
    auto = np.isin(mode,AUTO_MODES)
    balance = mode==3
    strict = np.array([abs(float(wrap(s['theta'])))<=.15 and abs(s['omega'])<=.5 and abs(s['x'])<=.05 and abs(s['velocity'])<=.05 and s['fault']==0 for s in states]) & auto
    pairs = paired(trial,lag)
    dynamic = [r for r in pairs if r['mode'] in AUTO_MODES]
    near = [r for r in dynamic if abs(r['encoder_rad'])<=.25 and abs(r['encoder_rate_rad_s'])<=.5]
    rests = {label:rest_report(trial,label) for label in RESTS}
    groups = {name:discrepancy([r for r in dynamic if predicate(r)]) for name,predicate in (
        ('positive_rate',lambda r:r['encoder_rate_rad_s']>.3),('negative_rate',lambda r:r['encoder_rate_rad_s']<-.3),
        ('low_speed',lambda r:abs(r['encoder_rate_rad_s'])<=.3),('BAL_mode',lambda r:r['mode']==3),
        ('SWINGUP_mode',lambda r:r['mode']==2),('cart_center',lambda r:abs(r['cart_step_m'])<=.05),
        ('cart_outer',lambda r:abs(r['cart_step_m'])>.05))}
    bins = []
    for center in np.arange(-165,180,30):
        selected = [r for r in dynamic if abs(float(wrap(r['encoder_rad']-math.radians(center))))<math.radians(15)]
        bins.append(dict(center_encoder_deg=int(center),all=discrepancy(selected),
            positive=discrepancy([r for r in selected if r['encoder_rate_rad_s']>.3]),
            negative=discrepancy([r for r in selected if r['encoder_rate_rad_s']<-.3])))
    pt = np.array([r['host_s'] for r in dynamic])
    strict_camera = np.array([abs(r['camera_rad'])<=.15 and r['camera_rate_rad_s'] is not None and abs(r['camera_rate_rad_s'])<=.5 and abs(r['encoder_rad'])<=.15 and abs(r['encoder_rate_rad_s'])<=.5 and abs(r['cart_step_m'])<=.05 and abs(r['cart_step_velocity_m_s'])<=.05 for r in dynamic])
    first_auto = next((host[i] for i in range(len(host)) if auto[i]),None)
    first_balance = next((host[i] for i in range(len(host)) if balance[i]),None)
    board_gaps = np.diff(trial['board'])
    camera_gaps = np.diff([c['t'] for c in trial['camera']])
    summary = dict(trial=trial['name'],source=str(trial['path']),collector_success=trial['report'].get('success'),
        collector_error=trial['report'].get('error'),
        native_info_diagnostics={key:sorted({i[key] for i in trial['infos'] if i.get(key) is not None}) for key in ('home_epoch','i2c_errors','encoder_recoveries','mag_status','encoder_conf','encoder_conf_valid')},
        reference_counts=trial['reference'],fixed_reference=trial['reference'] is not None,
        parameters=trial['report'].get('test_parameters',trial['report'].get('parameters',trial['report'].get('parameters_before'))),
        hardware_accepted=False,physical_balance_accepted=False,clock=trial['clock'],camera_filters=trial['filter_report'],
        telemetry=dict(samples=len(states),board_gap_s=stats(board_gaps),gaps_over_30ms=int((board_gaps>GAP_S+1e-9).sum()),
            camera_gap_s=stats(camera_gaps),camera_gaps_over_75ms=int((camera_gaps>CAMERA_GAP_S).sum()),
            max_abs_cart_step_m=float(max(abs(s['x']) for s in states)),
            max_abs_cart_auto_step_m=max((abs(s['x']) for s in states if s['mode'] in AUTO_MODES),default=None)),
        rests=rests,rest_differentials={f'{a}_to_{b}':rest_difference(rests[a],rests[b]) for a,b in (
            ('initial_rest','before_auto_rest'),('before_auto_rest','after_auto_rest'),('initial_rest','after_auto_rest'))},
        native=dict(auto_mode_duration=durations(host,auto),balance_mode_duration=durations(host,balance),
            full_home_mode_duration=durations(host,mode==13),counted_return_mode_duration=durations(host,mode==14),
            time_to_first_balance_s=None if first_auto is None or first_balance is None else float(first_balance-first_auto)),
        strict_encoder_and_step_hold=durations(host,strict),
        strict_camera_encoder_and_step_hold=durations(pt,strict_camera,[r['segment'] for r in dynamic],max_gap=CAMERA_GAP_S),
        paired_samples=len(pairs),auto_disagreement=discrepancy(dynamic),near_upright_low_speed=discrepancy(near),
        direction_and_state_groups=groups,angle_bins=bins,
        interpretation='Native BAL mode is controller state, not physical balance. Strict thresholds are observed angle/rate plus step-estimated cart position/velocity. Image vertical is not independently measured gravity vertical. Direction/state groups are confounded by pose, speed, load and camera geometry; no causal slip/hysteresis conclusion.')
    return summary,pairs


def plot_trial(trial,pairs,output):
    import os
    import tempfile
    os.environ.setdefault('MPLCONFIGDIR',str(Path(tempfile.gettempdir())/'encoder-tightening-matplotlib-cache'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    origin = trial['host'][0]
    fig,axes = plt.subplots(3,1,figsize=(12,8),sharex=True,layout='constrained')
    t = trial['host']-origin
    def broken_line(ax,x,y,segments=None,**options):
        if not len(x): return
        x,y=np.array(x,dtype=float),np.array(y,dtype=float)
        cut=np.r_[False,np.diff(x)>GAP_S] if segments is None else np.r_[False,(np.diff(x)>CAMERA_GAP_S)|(np.diff(segments)!=0)]
        # Duplicated NaN separators keep both observed endpoints visible.
        xx=[];yy=[]
        for i in range(len(x)):
            if cut[i]:xx.append(np.nan);yy.append(np.nan)
            xx.append(x[i]);yy.append(y[i])
        ax.plot(xx,yy,**options)
    theta=np.degrees([s['theta'] for s in trial['states']])%360
    # Equivalent 0..360 branch keeps both hanging sensors near180 degrees;
    # break plotted lines at the upright0/360 branch cut.
    theta[1:][abs(np.diff(theta))>180]=np.nan
    broken_line(axes[0],t,theta,label='Direct encoder θ',lw=.8)
    camera=trial['camera'];ct=np.array([c['t']-origin for c in camera]);cs=[c['segment'] for c in camera]
    ca=np.degrees([c['angle'] for c in camera])%360;ca[1:][abs(np.diff(ca))>180]=np.nan
    broken_line(axes[0],ct,ca,cs,label='Raw image vertical geometry',lw=.8,alpha=.8)
    broken_line(axes[1],[r['host_s']-origin for r in pairs],np.degrees([r['residual_rad'] for r in pairs]),[r['segment'] for r in pairs],label='Camera − encoder, frozen lag',lw=.8)
    broken_line(axes[2],t,[1000*s['x'] for s in trial['states']],label='Step-estimated cart position',lw=.8)
    axes[0].set_ylabel('Angle (deg, 0–360)');axes[1].set_ylabel('Residual (degrees)');axes[2].set_ylabel('Cart (mm)');axes[2].set_xlabel('Mapped host time from first state (s)')
    for label in RESTS:
        bounds=phase_bounds(trial,label)
        if bounds:
            for ax in axes:ax.axvspan(bounds[0]-origin,bounds[1]-origin,color='#98c9b3',alpha=.15)
    for ax in axes:
        ax.grid(alpha=.2)
        if ax.get_legend_handles_labels()[0]:ax.legend(loc='upper right')
    fig.suptitle(trial['name']+' — raw sensor comparison; no acceptance promotion')
    fig.savefig(output/(trial['name']+'.png'),dpi=160)
    native_times=[trial['host'][i]-origin for i,s in enumerate(trial['states']) if s['mode'] in AUTO_MODES]
    if native_times:
        axes[-1].set_xlim(native_times[0]-1,native_times[-1]+1)
        fig.suptitle(trial['name']+' — native AUTO interval; frozen lag comparison')
        fig.savefig(output/(trial['name']+'-auto.png'),dpi=160)
    plt.close(fig)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--lag-from',type=Path,help='Reuse a prior analysis report frozen lag without fitting any trial.')
    a=parser.parse_args(argv)
    root=a.input.resolve()
    paths=[root] if (root/'report.json').exists() else sorted({p.parent for p in root.rglob('report.json')})
    if not paths:parser.error('no trial report.json found')
    trials,excluded,extra_sources=[],[],[]
    for path in paths:
        extra_sources.extend([path/'report.json', *path.glob('rig*.jsonl'), *path.glob('vision*.json*'), *path.glob('vision.ndjson')])
        try:
            if not (path/'vision.ndjson').exists():
                excluded.append(dict(trial=path.name,reason='No raw camera stream; diagnostic preflight retained in source hashes.'))
                continue
            trial=load_trial(path)
            if trial['report'].get('success') is False and not any(s['mode'] in AUTO_MODES for s in trial['states']):
                excluded.append(dict(trial=path.name,reason='Collector failed before any native AUTO mode; retained source hashes.',collector_error=trial['report'].get('error')))
            else:
                trials.append(trial)
        except (ValueError,KeyError) as exc:
            excluded.append(dict(trial=path.name,reason=str(exc)))
    if not trials:parser.error('no analyzable trials; '+repr(excluded))
    trials.sort(key=lambda t:t['receipt'][0])
    a.output.mkdir(parents=True,exist_ok=False)
    if a.lag_from:
        lag=dict(read_json(a.lag_from)['frozen_lag'])
        if not lag.get('available') or not math.isfinite(lag['lag_s']) or abs(lag['lag_s'])>.1:
            raise ValueError('prior report must have an available finite lag within +/-100ms')
        lag['reused_from_report']=str(a.lag_from.resolve())
        extra_sources.append(a.lag_from)
    else:
        first_auto=next((t for t in trials if any(s['mode'] in (2,3) for s in t['states'])),trials[0])
        lag=fit_lag(first_auto)
    summaries=[]
    for trial in trials:
        summary,pairs=trial_summary(trial,lag['lag_s'])
        summaries.append(summary)
        (a.output/(trial['name']+'-pairs.ndjson')).write_text(''.join(json.dumps(row,allow_nan=False)+'\n' for row in pairs))
        plot_trial(trial,pairs,a.output)
    manifest=[dict(path=str(p),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted({p for t in trials for p in t['sources']}|set(extra_sources))]
    report=dict(schema='post-tightening-offline-analysis-v1',hardware_accepted=False,physical_balance_accepted=False,
        source_hashes=manifest,excluded_trials=excluded,script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),frozen_lag=lag,
        methodology=dict(encoder='Direct STATE.theta; reconstructed counts=(saved reference+theta*4096/(2π)) mod4096; current firmware ENC_INVERT=0. INFO.encoder_raw is reported separately. encoder_raw_age_us means time since raw count last changed, not acquisition freshness; it is never a freshness filter.',
            camera='atan2(bob.x-pivot.x,pivot.y-bob.y), raw marker geometry relative to image vertical. No calibrated/fused theta or mirrored encoder packets.',
            filters='Unique increasing source frames; detected measured track, stale=False, no worker error; confidence>=0.8; source age, host-source and collector receipt minus clock-mapped source<=150ms; length>5px and within20% of per-trial accepted median.',
            gaps='No encoder interpolation across >30ms; rejected camera tracks break segments; camera edges>75ms break camera holds/plots. No out-of-range extrapolation.',
            lag='Fit first chronological native AUTO trial only, never full HOME; frozen for later runs. Per-trial board lower-envelope and recorded camera clock anchors remain distinct from fitted lag.',
            rest_quality='Independently qualify >=100 disabled healthy states across>=4.5s with raw angle span<=0.03rad, max|omega|<=0.15 and step span<=3mm. Camera coverage requires>=30validframes, >=80%valid and >=75%windowspan; sparse measurements remain reported but unqualified.',
            thresholds='Strict: |angle|<=0.15rad, |rate|<=0.5rad/s, |step cart|<=0.05m, |step velocity|<=0.05m/s. Near-upright comparison: |encoder angle|<=0.25rad and |encoder rate|<=0.5rad/s.',
            limitations='No independent metric cart motion or gravity-vertical measurement; finite samples and latency/geometry errors can mimic sensor disagreement. No new calibration or hardware acceptance.'),trials=summaries)
    (a.output/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(output=str(a.output),lag={k:v for k,v in lag.items() if k!='grid'},trials=[dict(name=s['trial'],rests=s['rest_differentials'],native=s['native'],strict=s['strict_camera_encoder_and_step_hold'],disagreement=s['auto_disagreement'],near_upright=s['near_upright_low_speed'],gaps=s['telemetry']) for s in summaries]),indent=2))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
