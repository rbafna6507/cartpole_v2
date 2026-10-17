#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=1.26,<3", "matplotlib>=3.9,<4"]
# ///
"""Offline raw camera pixels versus counted cart position, one pulse per run.

Repeat --run DIRECTORY; plain or gzip Rig/vision logs supported. Assert
--same-host-clocks only when direct Rig received_ns and raw vision.t came from
one host monotonic clock. Output is a new directory; nothing is overwritten.
No SDK import, device, network, calibration or physical metric-gain claim.
"""
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import numpy as np

MAX_BYTES=256*1024*1024
MAX_LINE=4*1024*1024
FIT_WINDOW=(-.1,1.1)
LAGS=np.arange(-100,101,5,dtype=float)/1000


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def finite(x):return type(x) in (int,float) and math.isfinite(x)

def load_jsonl(path):
    rows=[];h=hashlib.sha256();total=0
    with (gzip.open(path,'rb') if path.suffix=='.gz' else path.open('rb')) as f:
        while True:
            line=f.readline(MAX_LINE+1)
            if not line:break
            total+=len(line)
            if len(line)>MAX_LINE or total>MAX_BYTES or len(rows)>=500_000:raise ValueError('source size bound exceeded')
            h.update(line)
            row=json.loads(line,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('nonfinite JSON')))
            if not isinstance(row,dict):raise ValueError('JSONL object required')
            rows.append(row)
    return rows,dict(path=str(path.resolve()),file_sha256=sha(path),decompressed_sha256=h.hexdigest(),records=len(rows),decompressed_bytes=total)


def clock_proxy(board_s,received_s):
    """OLS receipt mapping; offset conflates unknown one-way transport delay."""
    b=np.asarray(board_s,float);r=np.asarray(received_s,float)
    if len(b)<8 or b.shape!=r.shape or not np.isfinite(b).all() or not np.isfinite(r).all() or np.any(np.diff(b)<=0) or np.any(np.diff(r)<0):
        raise ValueError('invalid or reversed source clock')
    x=b-b[0];y=r-r[0];offset,slope=np.linalg.lstsq(np.column_stack((np.ones(len(x)),x)),y,rcond=None)[0]
    if slope<=0:raise ValueError('invalid fitted clock slope')
    mapped=r[0]+offset+slope*x;residual=r-mapped
    unit=r[0]+x+float(np.median(y-x))
    return mapped,dict(method='OLS received_host_s = receipt_origin_s + intercept_s + slope*(board_s-board_origin_s)',
        board_origin_s=float(b[0]),receipt_origin_s=float(r[0]),intercept_s=float(offset),slope=float(slope),slope_ppm=float((slope-1)*1e6),
        samples=len(b),residual_rmse_ms=float(np.sqrt(np.mean(residual**2))*1000),residual_p95_abs_ms=float(np.quantile(abs(residual),.95)*1000),
        residual_min_max_ms=[float(min(residual)*1000),float(max(residual)*1000)],
        max_difference_from_unit_slope_median_offset_ms=float(max(abs(unit-mapped))*1000),calibrated_latency=False,
        caveat='Board acquisition snapshot to host receipt proxy. Slope includes receipt jitter/trend; intercept includes unmeasured transport. Camera t is host-read, not exposure time.')


def interpolate_supported(t,x,queries,max_gap=.03):
    t=np.asarray(t,float);x=np.asarray(x,float);q=np.asarray(queries,float)
    if len(t)<2 or t.shape!=x.shape or np.any(np.diff(t)<=0):raise ValueError('strict interpolation times required')
    right=np.searchsorted(t,q,side='right');left=np.maximum(0,right-1);right=np.minimum(right,len(t)-1)
    exact=np.isclose(q,t[left],atol=1e-10,rtol=0)
    good=(q>=t[0])&(q<=t[-1])&(exact|((t[right]-t[left])<=max_gap))
    y=np.full(q.shape,np.nan);y[good]=np.interp(q[good],t,x);return y


def camera_frames(rows):
    frames=[];previous=None;duplicates=0;dimensions=set()
    for row in rows:
        if row.get('schema')!='cartpole-sensing-stream-v1':raise ValueError('wrong camera schema')
        v=row.get('vision',{});t=v.get('t');seq=v.get('seq')
        if not finite(t) or type(seq) is not int:raise ValueError('camera source identity missing')
        identity=(seq,t)
        if previous is not None:
            if identity==previous:duplicates+=1;continue
            if seq<=previous[0] or t<=previous[1]:raise ValueError('reversed camera frame identity')
        previous=identity;p=v.get('pivot_px');confidence=v.get('confidence')
        valid=(isinstance(p,(list,tuple)) and len(p)==2 and all(finite(z) for z in p) and finite(confidence) and confidence>=.5 and
            v.get('detected') is True and v.get('stale') is False and not v.get('worker_error'))
        dimensions.add((v.get('frame_width'),v.get('frame_height')))
        frames.append(dict(t=float(t),seq=seq,x_px=float(p[0]) if valid else None,y_px=float(p[1]) if valid else None,
            length_px=v.get('length_px') if finite(v.get('length_px')) else None,valid=bool(valid)))
    if len(dimensions)>1:raise ValueError('camera dimensions changed within run')
    return frames,dict(unique_frames=len(frames),valid_frames=sum(f['valid'] for f in frames),duplicate_frames=duplicates,
        dimensions=[list(x) for x in dimensions],source='raw vision.pivot_px only; mirrored/fused fields ignored',
        physical_camera_pose_certified=False)


def fit_line(x,y,lag):
    coef=np.linalg.lstsq(np.column_stack((np.ones(len(x)),x)),y,rcond=None)[0];error=y-(coef[0]+coef[1]*x)
    return dict(lag_s=float(lag),samples=len(x),intercept_px=float(coef[0]),gain_px_per_counted_m=float(coef[1]),
        rmse_px=float(np.sqrt(np.mean(error**2))),p95_abs_error_px=float(np.quantile(abs(error),.95)),
        max_abs_error_px=float(max(abs(error))),r_squared=float(1-np.sum(error**2)/np.sum((y-np.mean(y))**2)) if np.std(y)>0 else None)


def shape_fit(board_host_relative_s,x_m,camera_relative_s,pivot_x_px):
    t=np.asarray(board_host_relative_s,float);x=np.asarray(x_m,float);vt=np.asarray(camera_relative_s,float);p=np.asarray(pivot_x_px,float)
    window=(vt>=FIT_WINDOW[0])&(vt<=FIT_WINDOW[1])&np.isfinite(p);vt=vt[window];p=p[window]
    interpolated=[interpolate_supported(t,x,vt-lag) for lag in LAGS]
    support=np.all(np.isfinite(interpolated),axis=0)
    if sum(support)<20:raise ValueError('insufficient common camera/board support for lag comparison')
    xx=np.asarray(interpolated)[:,support];vt=vt[support];p=p[support]
    if min(np.ptp(xx,axis=1))<.001:raise ValueError('insufficient counted cart motion')
    fits=[fit_line(values,p,lag) for values,lag in zip(xx,LAGS)];best=min(fits,key=lambda r:r['rmse_px']);zero=fits[list(LAGS).index(0.)]
    return dict(fit_window_s=list(FIT_WINDOW),camera_points_before_board_support=len(window[window]),common_samples=len(vt),
        excluded_for_board_gap_or_bounds=int(sum(window)-sum(support)),zero_lag=zero,best_lag_diagnostic=best,lag_sensitivity=fits,
        lag_definition='Compare pivot_x(t) with counted_x(t-lag); positive lag means camera pixels trail the receipt-mapped count. Same-run fitted, not calibrated latency.',
        metric_scale_independently_established=False,
        points=[dict(t_s=float(tm),pivot_x_px=float(y),counted_x_m=float(a),zero_prediction_px=float(zero['intercept_px']+zero['gain_px_per_counted_m']*a)) for tm,y,a in zip(vt,p,xx[list(LAGS).index(0.)])])


def window_stats(frames,lo,hi):
    chosen=[f for f in frames if lo<=f['t_relative_s']<=hi];valid=[f for f in chosen if f['valid']]
    out=dict(window_s=[lo,hi],frames=len(chosen),valid_frames=len(valid),coverage=len(valid)/len(chosen) if chosen else None,
        max_valid_frame_gap_s=max((b['t']-a['t'] for a,b in zip(valid,valid[1:])),default=None))
    if valid:
        for key in ('x_px','y_px','length_px'):
            v=[f[key] for f in valid if f[key] is not None]
            out[key]=dict(median=float(np.median(v)),p05=float(np.quantile(v,.05)),p95=float(np.quantile(v,.95))) if v else None
    return out


def analyze_run(directory):
    directory=Path(directory);report_path=directory/'report.json';report=json.loads(report_path.read_text())
    if report.get('schema')!='cartpole-id-run-v1' or report.get('procedure')!='pulse' or report.get('completed') is not True or report.get('stop_confirmed') is not True or report.get('records_dropped')!=0 or report.get('failure') or report.get('camera',{}).get('failure'):
        raise ValueError('bound completed pulse report required')
    def locate(name):
        p=directory/name
        if p.exists():return p
        if p.with_name(p.name+'.gz').exists():return p.with_name(p.name+'.gz')
        raise FileNotFoundError(p)
    records,rig_pin=load_jsonl(locate(report['raw_log']));vision,vision_pin=load_jsonl(locate('vision.ndjson'))
    if rig_pin['decompressed_sha256']!=report['raw_log_sha256'] or vision_pin['decompressed_sha256']!=report['camera'].get('sha256'):
        raise ValueError('raw source/report hash mismatch')
    states=[];duplicates=0
    for row in records:
        if row.get('type') in ('error','ringdown_failure','collection_failure','stop_failure'):raise ValueError('failed raw collection')
        if row.get('type')=='termination' and (row.get('error') is not None or row.get('records_dropped',0)!=0):raise ValueError('failed raw termination')
        if row.get('type')!='state':continue
        s=row['state']
        if states and s['unwrapped_us']==states[-1]['unwrapped_us']:
            fields=lambda z:{k:v for k,v in z.items() if k!='received_ns'}
            if fields(s)!=fields(states[-1]):raise ValueError('contradictory board duplicate')
            duplicates+=1;continue
        if s.get('fault')!=0 or s.get('flags',0)&13!=13 or s.get('flags',0)&304:raise ValueError('unhealthy source state')
        states.append(s)
    sessions={s['sid'] for s in states}
    if len(sessions)!=1:raise ValueError('one source session required')
    b=np.array([s['unwrapped_us']/1e6 for s in states]);r=np.array([s['received_ns']/1e9 for s in states]);x=np.array([s['x'] for s in states])
    if not np.isfinite(x).all():raise ValueError('finite counted cart position required')
    mapped,mapping=clock_proxy(b,r);refs=[z for z in records if z.get('type')=='ringdown_reference']
    if not refs:raise ValueError('pulse board origin missing')
    origin_board=refs[0]['board_ns']/1e9;origin=mapping['receipt_origin_s']+mapping['intercept_s']+mapping['slope']*(origin_board-mapping['board_origin_s'])
    frames,camera=camera_frames(vision)
    for f in frames:f['t_relative_s']=f['t']-origin
    valid=[f for f in frames if f['valid']];vt=np.array([f['t_relative_s'] for f in valid]);px=np.array([f['x_px'] for f in valid])
    if not len(vt) or vt[-1]<0 or vt[0]>1:raise ValueError('camera/board host clocks do not overlap pulse')
    shape=shape_fit(mapped-origin,x,vt,px)
    end=.65+float(report['result']['hold_seconds']);baseline=window_stats(frames,-.25,-.05);tail=window_stats(frames,max(.85,end-1),end)
    difference=(tail['x_px']['median']-baseline['x_px']['median']) if baseline.get('x_px') and tail.get('x_px') else None
    baseline_x=x[((mapped-origin)>=-.25)&((mapped-origin)<=-.05)];tail_x=x[((mapped-origin)>=max(.85,end-1))&((mapped-origin)<=end)]
    return dict(run=directory.name,source_hashes=dict(report=sha(report_path),rig=rig_pin,vision=vision_pin),session_id=next(iter(sessions)),
        amplitude_m=report['result']['amplitude_m'],duplicate_board_states=duplicates,timing_proxy=mapping,origin_board_s=origin_board,origin_host_proxy_s=origin,
        camera=camera,pulse_geometry=window_stats(frames,*FIT_WINDOW),baseline=baseline,tail=tail,
        apparent_return_offset_px=difference,counted_return_offset_m=float(np.median(tail_x)-np.median(baseline_x)) if len(tail_x) and len(baseline_x) else None,
        shape=shape,raw_points=[dict(t_s=f['t_relative_s'],x_px=f['x_px'],y_px=f['y_px']) for f in frames],
        counted_points=[[float(t),float(v)] for t,v in zip(mapped-origin,x)])


def draw(runs,out):
    import matplotlib;matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(len(runs),2,figsize=(13,3*len(runs)),squeeze=False,layout='constrained')
    for row,run in enumerate(runs):
        raw=run['raw_points'];valid=[p for p in raw if p['x_px'] is not None];t=np.array([p['t_s'] for p in valid]);p=np.array([p['x_px'] for p in valid]);base=run['baseline'].get('x_px',{}).get('median',float(np.median(p)))
        counted=np.array(run['counted_points']);zero=run['shape']['zero_lag'];best=run['shape']['best_lag_diagnostic']
        for ax in axes[row]:ax.scatter(t,p-base,s=9,color='#1766a0',label='Raw pivot pixels');ax.axhline(0,color='#888',lw=.6);ax.set_xlabel('Seconds from pulse start, receipt clock proxy');ax.set_ylabel('Pivot x − pre-pulse median (px)');ax.grid(alpha=.2)
        axes[row,0].plot(counted[:,0],zero['intercept_px']+zero['gain_px_per_counted_m']*counted[:,1]-base,color='#d56720',label='Counted x, fitted px/count scale')
        axes[row,0].set_xlim(-.25,1.25);axes[row,1].set_xlim(-.25,max(counted[:,0]))
        axes[row,0].set_title(f"{run['run']}: zero-proxy-lag RMSE {zero['rmse_px']:.2f} px; fitted gain {zero['gain_px_per_counted_m']:.0f} px/m")
        axes[row,1].set_title(f"Return offset {run['apparent_return_offset_px']:.2f} px; best same-run lag {best['lag_s']*1000:.0f} ms")
    axes[0,0].legend(fontsize=8);fig.suptitle('Camera pixels versus counted motion: diagnostic scale and timing only',fontsize=15)
    fig.savefig(out/'camera-vs-step.png',dpi=160);fig.savefig(out/'camera-vs-step.pdf');plt.close(fig)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',action='append',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--same-host-clocks',action='store_true',help='Assert all raw vision.t and Rig received_ns came from the same host monotonic clock.');p.add_argument('--no-plot',action='store_true');a=p.parse_args(argv)
    if not a.same_host_clocks:p.error('--same-host-clocks assertion required')
    if a.output.exists():p.error('output must be new')
    runs=[analyze_run(d) for d in a.run];gains=np.array([r['shape']['zero_lag']['gain_px_per_counted_m'] for r in runs]);baseline=[r['baseline'].get('x_px',{}).get('median') for r in runs]
    result=dict(schema='cartpole-camera-step-pulse-diagnostic-v1',scope='Retrospective per-run pixel/count shape, timing-proxy sensitivity and apparent return; no independent metric gain, calibrated latency or slip certification.',
        same_host_clocks_operator_asserted=True,independent_metric_scale=False,calibrated_latency=False,physical_stationarity_certified=False,
        input_source='Direct Rig STATE x/received_ns and raw vision.t/pivot_px only; SDK filters, old camera calibration and mirrored encoder unused.',
        runs=runs,cross_run_consistency=dict(gain_mean_px_per_counted_m=float(np.mean(gains)),gain_std_px_per_counted_m=float(np.std(gains)),gain_min_max_px_per_counted_m=[float(min(gains)),float(max(gains))],baseline_pivot_x_px=baseline,interpretation='Four different sign/amplitude conditions, not repeated trials at each condition; no statistical repeatability estimate. Different camera poses cannot be excluded from geometry alone.'),
        caveats=['Within-run pixel/count regression is descriptive and cannot establish independent cart metric scale or physical input gain.','Best lag is selected on these same observations and conflates receipt mapping, exposure/readout/processing, commanded/physical differences and detector jitter; it is not calibrated latency.','No missing camera points are filled. Counted x interpolation uses adjacent source states only and excludes gaps over30ms. Lag fits use identical common camera support.','Raw arm pivot may move with contour/pose estimation; no independent fixed-background landmark measurement is available here. Apparent offsets do not uniquely establish slip.'],
        provenance=dict(script_sha256=sha(__file__),numpy_version=np.__version__,lag_grid_s=LAGS.tolist(),fit_window_s=list(FIT_WINDOW)))
    payload=json.dumps(result,indent=2,allow_nan=False)+'\n';a.output.mkdir(parents=True,exist_ok=False);(a.output/'analysis.json').write_text(payload)
    if not a.no_plot:draw(runs,a.output)
    print(json.dumps(dict(output=str(a.output),runs=[dict(run=r['run'],zero_lag=r['shape']['zero_lag'],best_lag=r['shape']['best_lag_diagnostic'],return_offset_px=r['apparent_return_offset_px'],geometry_coverage=r['pulse_geometry']['coverage']) for r in runs]),indent=2))

if __name__=='__main__':main()
