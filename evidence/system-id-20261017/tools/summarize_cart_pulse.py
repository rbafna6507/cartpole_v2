#!/usr/bin/env python3
"""Summarize an immutable cart-pulse directory; no hardware access or model fit.

Usage: ./summarize_cart_pulse.py RUN_DIRECTORY --output NEW_SUMMARY.json
Optional --columns NEW.json.gz retains exact selected values for portable plots.
Cart x/v/a are executor estimates; camera coordinates are uncalibrated pixels.
"""
import argparse,gzip,hashlib,json,math,statistics
from pathlib import Path

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def extent(rows,k):
    v=[r[k] for r in rows if r.get(k) is not None]
    if k in ('theta','image_angle_rad') and v:
        unwrapped=[v[0]]
        for previous,current in zip(v,v[1:]):unwrapped.append(unwrapped[-1]+math.atan2(math.sin(current-previous),math.cos(current-previous)))
        v=unwrapped
    return dict(min=min(v),max=max(v),span=max(v)-min(v)) if v else None

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--columns',type=Path);a=p.parse_args()
    for output in (a.output,a.columns):
        if output and output.exists():raise ValueError('output exists: '+str(output))
    base=a.run;rdir=base/'rig' if (base/'rig').is_dir() else base;vdir=base/'vision' if (base/'vision').is_dir() else base;report=json.loads((rdir/'report.json').read_text());logs=list(rdir.glob('rig-*.jsonl'))
    if len(logs)!=1:raise ValueError('one raw rig log required')
    log=logs[0]
    if digest(log)!=report['raw_log_sha256']:raise ValueError('raw log hash mismatch')
    records=[json.loads(l) for l in log.open()];states=[r['state'] for r in records if r['type']=='state'];refs=[r for r in records if r['type']=='ringdown_reference'];start=next((r for r in records if r['type']=='ringdown_start'),None)
    vision=vdir/'vision.ndjson';vr=json.loads((vdir/'vision-report.json').read_text());vv=[json.loads(l)['vision'] for l in vision.open()]
    if digest(vision)!=vr['sha256']:raise ValueError('vision hash mismatch')
    valid=[v for v in vv if v.get('detected') is True and v.get('pivot_px') is not None and v.get('image_angle_rad') is not None and (v.get('confidence') or 0)>=.5]
    gaps=[(b['board_ns']-c['board_ns'])/1e6 for c,b in zip(refs,refs[1:])];hostgaps=[(b['host_policy_ns']-c['host_policy_ns'])/1e6 for c,b in zip(refs,refs[1:])]
    stop=[r for r in records if r['type']=='ringdown_stop']
    def part(rows):
        return {k:extent(rows,k) for k in ('x','v','theta','omega','command')}
    pivot=[dict(px=v['pivot_px'][0],py=v['pivot_px'][1]) for v in valid]
    out=dict(run=base.name,failure=report.get('failure'),records_dropped=report['records_dropped'],source_hashes={str(log.relative_to(base)):digest(log),str(vision.relative_to(base)):digest(vision),str((rdir/'report.json').relative_to(base)):digest(rdir/'report.json'),str((vdir/'vision-report.json').relative_to(base)):digest(vdir/'vision-report.json')},
        samples=len(states),policy_samples=len(refs),duration_board_s=refs[-1]['t_s'] if refs else None,max_policy_board_gap_ms=max(gaps,default=None),max_policy_host_gap_ms=max(hostgaps,default=None),
        pulse=part([r for r in refs if r['phase']=='pulse']),tail=part([r for r in refs if r['phase']!='pulse']),reference_start=start,stop=stop[-1] if stop else None,
        fault_codes=sorted({s['fault'] for s in states}),max_abs_applied_acceleration_m_s2=max(abs(s['acceleration']) for s in states),
        vision=dict(frames=len(vv),valid_geometry=len(valid),coverage=len(valid)/len(vv) if vv else 0,image_angle=extent(valid,'image_angle_rad'),pivot_x=extent(pivot,'px'),pivot_y=extent(pivot,'py'),max_valid_gap_s=max((b['t']-c['t'] for c,b in zip(valid,valid[1:])),default=None),failure=vr.get('failure')),
        interpretation='Cart x/v/a use step-count/command telemetry; camera pixels have no independent metric scale. Feedback tail is forced and not a passive cart-fixed experiment.')
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2,allow_nan=False)+'\n')
    if a.columns:
        skeys=['unwrapped_us','received_ns','tick','theta','angle_hat','omega','x','velocity','acceleration','flags','fault','mode','last_seq'];vkeys=['seq','t','detected','image_angle_rad','pivot_px','bob_px','cart_pivot_px','length_px','confidence','detection_status','host_read_to_result_ms'];rkeys=['t_s','board_ns','host_policy_ns','phase','x_reference','v_reference','a_reference','jerk_reference','x','v','theta','omega','command','clamped']
        data=dict(schema='cartpole-pulse-column-extract-v1',source_hashes=out['source_hashes'],report=report,vision_report=vr,state_columns=skeys,states=[[s[k] for k in skeys] for s in states],vision_columns=vkeys,vision=[[v.get(k) for k in vkeys] for v in vv],reference_columns=rkeys,references=[[r[k] for k in rkeys] for r in refs])
        a.columns.write_bytes(gzip.compress(json.dumps(data,separators=(',',':'),allow_nan=False).encode(),mtime=0))
    print(json.dumps({k:v for k,v in out.items() if k not in ('reference_start','source_hashes')},indent=2))
if __name__=='__main__':main()
