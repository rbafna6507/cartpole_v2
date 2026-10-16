#!/usr/bin/env python3
"""Offline diagnostic analysis; no physical-reference or calibration approval."""
import argparse
from pathlib import Path
import json,math,statistics,hashlib

COUNT_DEG=360/4096

def mean(a):return statistics.mean(a)
def stats(values):
    quarter=max(1,len(values)//4)
    return dict(n=len(values),mean=mean(values),median=statistics.median(values),minimum=min(values),maximum=max(values),
                span=max(values)-min(values),population_std=statistics.pstdev(values),
                first_last_quarter_median_drift=statistics.median(values[-quarter:])-statistics.median(values[:quarter]))
def image_down(v):
    return math.atan2(v['bob_px'][0]-v['pivot_px'][0],v['bob_px'][1]-v['pivot_px'][1])
def load_rows(p):return [json.loads(line) for line in p.read_text().splitlines()]
def difference(a,b):
    # D = encoder - vision. With unchanged calibration, delta vision=-delta image.
    ea,eb=a['_enc'],b['_enc'];ca,cb=a['_cam'],b['_cam']
    lo=min(eb)-max(ea)+min(cb)-max(ca);hi=max(eb)-min(ea)+max(cb)-min(ca)
    return dict(delta_raw_mean_counts=mean(b['_raw'])-mean(a['_raw']),
        delta_encoder_deg=mean(eb)-mean(ea),delta_image_down_deg=mean(cb)-mean(ca),
        delta_aligned_vision_deg=-(mean(cb)-mean(ca)),delta_encoder_minus_vision_deg=mean(eb)-mean(ea)+mean(cb)-mean(ca),
        independent_observed_extrema_envelope_deg=[lo,hi],
        observed_envelope_plus_encoder_quantization_deg=[lo-COUNT_DEG,hi+COUNT_DEG])
def clean(value):
    if isinstance(value,dict):return {k:clean(v) for k,v in value.items() if not k.startswith('_')}
    if isinstance(value,list):return [clean(v) for v in value]
    return value

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--source',required=True);ap.add_argument('--output',required=True)
    args=ap.parse_args();source=Path(args.source);runs=[];sources={};windows=[]
    for directory in sorted(source.iterdir(),key=lambda p:int(p.name.rsplit('-',1)[-1])):
        if not directory.is_dir():continue
        for p in directory.iterdir():
            if p.is_file():sources[str(p.relative_to(source))]=hashlib.sha256(p.read_bytes()).hexdigest()
        report=json.loads((directory/'summary.json').read_text());state_rows=load_rows(directory/'states.jsonl');vision_rows=load_rows(directory/'vision.jsonl')
        short=directory.name.removeprefix('calibration-screen-').rsplit('-',1)[0]
        run={'name':short,'directory':directory.name,'success':report['success'],'cart_direction':report['direction'],
             'error':report.get('error'),'events':report.get('events',[]),
             'shadow_valid_reported':report.get('shadow_valid'),
             'shadow_note':'positive1 predates shadow_valid field; its summary reports success with no source errors' if short=='positive1' else None,
             'initial_info':report['initial_info'],'final_info':report['final_info'],'final':report['final'],
             'excursion_end':report.get('excursion_end'),
             'parameter_change':report.get('parameters_before')!=report.get('parameters_after') if report['success'] else None,
             'windows':{}}
        for phase in ('baseline','after'):
            records=[r for r in state_rows if r['phase']==phase]
            camera_all=[r for r in vision_rows if r['phase']==phase]
            camera=[r for r in camera_all if r['snapshot'].get('angle_valid') and r['snapshot'].get('pivot_px') and r['snapshot'].get('bob_px')]
            if not records or not camera:continue
            states=[r['state'] for r in records];snaps=[r['snapshot'] for r in camera]
            raw=[r['raw_count'] for r in records];enc=[math.degrees(s['theta']) for s in states];cam=[math.degrees(image_down(v)) for v in snaps]
            for s,count in zip(states,raw):
                scaled=s['theta']*4096/math.tau
                assert abs(scaled-round(scaled))<=.001 and count==(370+round(scaled))%4096
            board_gaps=[b['unwrapped_us']-a['unwrapped_us'] for a,b in zip(states,states[1:])]
            recv=[s['received_ns']/1e9 for s in states];vt=[v['t'] for v in snaps]
            common_start=max(min(recv),min(vt))+.25;common_end=min(max(recv),max(vt))-.25
            selected_e=[i for i,t in enumerate(recv) if common_start<=t<=common_end]
            selected_v=[i for i,t in enumerate(vt) if common_start<=t<=common_end]
            calibs={json.dumps(v['calibration'],sort_keys=True,separators=(',',':')) for v in snaps}
            w={'phase':phase,'raw_counts':stats(raw),'encoder_deg':stats(enc),'image_down_deg':stats(cam),
               'state_count':len(states),'valid_camera_count':len(camera),'all_camera_count':len(camera_all),
               'actual_board_duration_s':(states[-1]['unwrapped_us']-states[0]['unwrapped_us'])/1e6,
               'board_gap_us':{'min':min(board_gaps),'max':max(board_gaps)},
               'conservative_fitter_duration_s':(len(states)-1)*min(board_gaps)/1e6,
               'unique_source_ticks':len({(s['sid'],s['unwrapped_tick']) for s in states})==len(states),
               'strict_board_time_order':all(gap>0 for gap in board_gaps),
               'host_receipt_order':all(b>=a for a,b in zip(recv,recv[1:])),
               'invalid_state_count':sum(not(s['flags']&1) or bool(s['flags']&258) or s['mode']!=0 or s['fault']!=0 for s in states),
               'state_x_m':stats([s['x'] for s in states]),'max_abs_omega_rad_s':max(abs(s['omega']) for s in states),
               'pivot_x_px':stats([v['pivot_px'][0] for v in snaps]),'pivot_y_px':stats([v['pivot_px'][1] for v in snaps]),
               'length_px':stats([v['length_px'] for v in snaps]),
               'source_calibration_sha256':[hashlib.sha256(c.encode()).hexdigest() for c in sorted(calibs)],
               'geometry_matches_snapshot_image_angle_max_error_rad':max(abs(image_down(v)-v['image_angle_rad']) for v in snaps),
               'snapshot_source_to_receipt_ms':stats([(r['received_ns']/1e9-r['snapshot']['t'])*1000 for r in camera]),
               'trimmed_common_host_interval_s':[common_start,common_end],
               '_enc':enc,'_raw':raw,'_cam':cam,
               '_trim':{'_enc':[enc[i] for i in selected_e],'_raw':[raw[i] for i in selected_e],'_cam':[cam[i] for i in selected_v]}}
            run['windows'][phase]=w
        if report['success']:
            a,b=run['windows']['baseline'],run['windows']['after']
            run['change']=difference(a,b);run['trimmed_change']=difference(a['_trim'],b['_trim'])
            run['home_pivot_mean_change_px']=[b[k]['mean']-a[k]['mean'] for k in ('pivot_x_px','pivot_y_px')]
            settling=[r['state']['received_ns'] for r in state_rows if r['phase']=='settling']
            run['recorded_settling_span_s']=(max(settling)-min(settling))/1e9 if settling else None
            windows.extend([a,b])
        runs.append(run)
    completed=[r for r in runs if r['success']]
    bridges=[]
    for a,b in zip(completed,completed[1:]):
        bridges.append({'from_run':a['name'],'to_run':b['name'],**difference(a['windows']['after'],b['windows']['baseline'])})
    all_cal={c for w in windows for c in w['source_calibration_sha256']}
    result={'analysis_version':'micro-motion-relative-rest-v1','sources_sha256':sources,'runs':runs,
      'completed_runs':len(completed),'aborted_pre_motion_runs':[r['name'] for r in runs if not r['success']],
      'chronological_after_to_next_baseline':bridges,
      'initial_to_final':difference(windows[0],windows[-1]),
      'initial_to_final_trimmed':difference(windows[0]['_trim'],windows[-1]['_trim']),
      'resting_window_raw_mean_range_counts':max(w['raw_counts']['mean'] for w in windows)-min(w['raw_counts']['mean'] for w in windows),
      'home_pivot_mean_range_px':{axis:max(w[axis]['mean'] for w in windows)-min(w[axis]['mean'] for w in windows) for axis in ('pivot_x_px','pivot_y_px')},
      'camera_calibration_constant':len(all_cal)==1,'camera_calibration_sha256':sorted(all_cal),
      'method':{'angle_sign':'aligned vision delta = - raw image-down-angle delta; D=encoder-vision so delta D=delta encoder+delta image',
       'window_statistics':'Original per-phase samples; no resampling/interpolation. Stability uses full range and first/last-quarter median drift. Means are descriptive only.',
       'bounds':'Independent observed extrema: [min(E_after)-max(E_before)+min(I_after)-max(I_before), max(E_after)-min(E_before)+max(I_after)-min(I_before)]. No sqrt(N), standard error, or independence assumption. An additional +/-one encoder count accounts for two half-count quantization terms.',
       'trim_sensitivity':'Remove250ms from both ends of the overlap of serial-host-receipt and camera-host-read intervals. These are different acquisition proxies; this is a boundary sensitivity check, not calibrated dynamic alignment.'},
      'limitations':['Observed sample envelopes do not bound camera systematic errors, out-of-plane pose changes, mechanical alignment, or physical-reference uncertainty.',
       'The cart has no calibrated visual x channel; zero step x plus a clustered image pivot corroborates counted-home repeatability but does not prove metric physical home error.',
       'Cart excursion direction is not the raw encoder approach direction required by CalibrationProfile.',
       'All windows are hanging observations; no fresh independent upright/hanging pair or physical upright uncertainty is supplied.',
       'positive2 shadow failed its receipt residual gate; raw native/camera data are analyzed independently, never substituted as valid fused output.',
       'Per-run executed script hashes were not captured in these directories; the available script is preserved separately as context, not proof that all runs executed identical code.'],
      'calibration_eligible_pairs':0,'control_eligible':False}
    Path(args.output).write_text(json.dumps(clean(result),indent=2)+'\n')
    print(json.dumps({'completed':len(completed),'initial_to_final':result['initial_to_final'],'trimmed':result['initial_to_final_trimmed']},indent=2))

if __name__=='__main__':main()
